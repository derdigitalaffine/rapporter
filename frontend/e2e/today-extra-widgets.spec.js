import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const widgetIds=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes','loyalty','inbox'];

function routineAction(routine){
  const status=routine.prediction?.status||'upcoming';const primary={id:'record_done',method:'POST',href:`/api/routines/${routine.id}/done/`};
  return {id:`routine:${routine.id}`,family:routine.family,kind:'routine',title:routine.name,state:status==='overdue'?'overdue':status==='due'?'due':'open',due_at:null,next_due_at:routine.prediction?.expected_at||null,completed_at:null,assignee:null,priority:'normal',urgency:status==='overdue'?'overdue':status==='due'?'high':'normal',context:{source:'routine',list:null,workflow:null},repeat:{target_count:1,target_period_days:1},tags:[],primary_action:primary,allowed_actions:[primary,{id:'snooze',method:'POST',href:`/api/routines/${routine.id}/snooze/`},{id:'edit',method:'PATCH',href:`/api/routines/${routine.id}/`}],deep_link:`/?page=routines&routine=${routine.id}`,ranking:{version:'actions-v1',bucket:status==='overdue'?0:status==='due'?3:5,reasons:[status==='overdue'?'overdue':status==='due'?'routine_due':'normal']}};
}

test('Today surfaces accessible loyalty cards and unread family inbox',async({page})=>{
  await installApiMocks(page);
  await page.route('**/api/today-layout/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,revision:0,widgets:widgetIds.map(id=>({id,visible:true,size:'full'}))})}));
  await page.route('**/api/inbox/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([{id:'message-1',family:'family-1',status:'new',title:'Familieninfo'}])}));
  await page.route('**/api/loyalty-cards/sync/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([{id:'card-1',family:'family-1',name:'REWE Bonus',favorite:true,holder_display:'Alex',barcode_format:'code128',barcode_value:'123456789',customer_number:'123456789',can_edit:true}])}));
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('today-loyalty')).toContainText('REWE Bonus');
  await expect(page.getByTestId('today-inbox')).toContainText('1 ungelesen');
  await Promise.all([
    page.waitForURL(/page=loyalty/),
    page.getByRole('button',{name:'REWE Bonus · Bonuskarten'}).click(),
  ]);
  const dialog=page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('heading',{name:'REWE Bonus'}).first()).toBeVisible();
});

test('Today routines prioritize overdue and due work inside the unified To-do widget',async({page})=>{
  const state=await installApiMocks(page);
  const future=new Date(Date.now()+5*86400000).toISOString();
  state.routines=[
    {id:'routine-recent',family:state.family.id,name:'Gerade erledigt',icon:'history',active:true,last_done_at:new Date().toISOString(),prediction:{status:'upcoming',expected_at:future}},
    {id:'routine-upcoming',family:state.family.id,name:'Demnächst',icon:'bed',active:true,last_done_at:null,prediction:{status:'upcoming',expected_at:future}},
    {id:'routine-due',family:state.family.id,name:'Heute fällig',icon:'droplets',active:true,last_done_at:null,prediction:{status:'due',expected_at:new Date().toISOString()}},
    {id:'routine-overdue',family:state.family.id,name:'Längst überfällig',icon:'sparkles',active:true,last_done_at:null,prediction:{status:'overdue',expected_at:new Date(Date.now()-86400000).toISOString()}},
  ];
  await page.route('**/api/actions/**',route=>{
    const order=['routine-overdue','routine-due','routine-upcoming','routine-recent'];const results=order.map(id=>routineAction(state.routines.find(row=>row.id===id)));
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:results.length,next:null,previous:null,results,ranking_version:'actions-v1',scope:'today'})});
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const widget=page.getByTestId('today-todos');
  await expect(widget).toContainText('4 offen');
  const rows=widget.locator('[data-action-id^="routine:"]');
  await expect(rows).toHaveCount(4);
  await expect(rows.nth(0)).toContainText('Längst überfällig');
  await expect(rows.nth(0)).toContainText('Überfällig');
  await expect(rows.nth(1)).toContainText('Heute fällig');
  await expect(rows.nth(2)).toContainText('Demnächst');
  await expect(rows.nth(3)).toContainText('Gerade erledigt');
});
