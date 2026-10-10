import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const widgetIds=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes','loyalty','inbox'];

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

test('Today routines prioritize overdue and due work instead of recently completed items',async({page})=>{
  const state=await installApiMocks(page);
  const future=new Date(Date.now()+5*86400000).toISOString();
  state.routines=[
    {id:'routine-recent',family:state.family.id,name:'Gerade erledigt',icon:'history',active:true,last_done_at:new Date().toISOString(),prediction:{status:'upcoming',expected_at:future}},
    {id:'routine-upcoming',family:state.family.id,name:'Demnächst',icon:'bed',active:true,last_done_at:null,prediction:{status:'upcoming',expected_at:future}},
    {id:'routine-due',family:state.family.id,name:'Heute fällig',icon:'droplets',active:true,last_done_at:null,prediction:{status:'due',expected_at:new Date().toISOString()}},
    {id:'routine-overdue',family:state.family.id,name:'Längst überfällig',icon:'sparkles',active:true,last_done_at:null,prediction:{status:'overdue',expected_at:new Date(Date.now()-86400000).toISOString()}},
  ];
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const widget=page.getByTestId('today-routines');
  await expect(widget).toContainText('2 fällig');
  const rows=widget.locator('.today-routine-row');
  await expect(rows).toHaveCount(4);
  await expect(rows.nth(0)).toContainText('Längst überfällig');
  await expect(rows.nth(0)).toContainText('Überfällig');
  await expect(rows.nth(1)).toContainText('Heute fällig');
  await expect(rows.nth(1)).toContainText('Jetzt fällig');
  await expect(rows.nth(2)).toContainText('Demnächst');
});
