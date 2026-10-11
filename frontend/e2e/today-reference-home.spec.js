import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function todayAt(hour){
  const now=new Date();
  const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(now);
  const read=type=>Number(parts.find(part=>part.type===type)?.value||0);
  const elapsed=((read('hour')*60+read('minute'))*60+read('second'))*1000;
  return new Date(now.getTime()-elapsed+hour*3600000).toISOString();
}
const widgetIds=['priority','next','weather','tasks','shopping','routines','waste','inbox','birthdays','notes','loyalty'];

function taskAction(task){
  const primary={id:task.completed_at?'reopen':'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`};
  return {id:`task:${task.id}`,family:task.family,kind:'task',title:task.title,state:task.completed_at?'done_today':'due',due_at:task.due_at,next_due_at:task.completed_at?null:task.due_at,completed_at:task.completed_at,assignee:{id:task.assignee,username:task.assignee_name},priority:task.priority,urgency:'high',context:{source:'manual',list:{id:task.task_list,name:task.list_name},workflow:null},repeat:null,tags:[],primary_action:primary,allowed_actions:[primary,{id:'edit',method:'PATCH',href:`/api/tasks/${task.id}/`}],deep_link:`/?page=tasks&task=${task.id}`,ranking:{version:'actions-v1',bucket:1,reasons:['due_today']}};
}
function routineAction(routine){
  const primary={id:'record_done',method:'POST',href:`/api/routines/${routine.id}/done/`};
  return {id:`routine:${routine.id}`,family:routine.family,kind:'routine',title:routine.name,state:'open',due_at:null,next_due_at:routine.prediction?.expected_at||null,completed_at:null,assignee:null,priority:'normal',urgency:'normal',context:{source:'routine',list:null,workflow:null},repeat:{target_count:1,target_period_days:1},tags:[],primary_action:primary,allowed_actions:[primary,{id:'snooze',method:'POST',href:`/api/routines/${routine.id}/snooze/`},{id:'edit',method:'PATCH',href:`/api/routines/${routine.id}/`}],deep_link:`/?page=routines&routine=${routine.id}`,ranking:{version:'actions-v1',bucket:5,reasons:['normal']}};
}

async function bootReference(page,viewport={width:390,height:844}){
  await page.setViewportSize(viewport);
  const state=await installApiMocks(page,{dismissOnboarding:true});
  const task={id:'home-task',family:'family-1',task_list:'tasks-1',title:'Paket abholen',notes:'',priority:'high',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:todayAt(14),completed_at:null};
  const routine={id:'routine-1',family:'family-1',name:'Pflanzen gießen',active:true,last_done_at:todayAt(8),prediction:{status:'learning'}};
  const dashboard={
    tasks:[task],task_lists:[{id:'tasks-1',family:'family-1',name:'Alltag',open_count:1,done_count:0}],
    shopping_lists:[{id:'shop-1',family:'family-1',name:'Supermarkt',open_count:2,checked_count:0,items:[{id:'milk',name:'Milch',quantity:'1 l',category:'Kühlung',checked:false},{id:'bread',name:'Brot',quantity:'1',category:'Backwaren',checked:false}]}],
    routines:[routine],
    events:[
      {id:'warn-1',family:'family-1',type:'public.warning',title:'Sturmwarnung',starts_at:todayAt(12),ends_at:todayAt(13),payload:{provider:'Warnamt'}},
      {id:'waste-1',family:'family-1',type:'waste.paper',title:'Papiertonne',starts_at:todayAt(22),payload:{provider:'Stadt'}},
      {id:'event-1',family:'family-1',type:'calendar.event',title:'Kinderarzt',starts_at:todayAt(16),ends_at:todayAt(17),payload:{location:'Praxis',provider:'FamilyOS'}}
    ],
    weather:{current:{temperature:17,apparent_temperature:16,weather_code:2,wind_speed:8,observed_at:new Date().toISOString()}},birthdays:[],inbox_count:1,automation_count:0
  };
  state.events=dashboard.events;
  const inbox=[{id:'message-1',family:'family-1',status:'new',unread:true,source:'manual_message',title:'Bitte Brotdose mitnehmen',body:'Bitte Brotdose mitnehmen',created_by_name:'Sam',created_at:todayAt(10)}];
  await page.route('**/api/dashboard/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard)}));
  await page.route('**/api/inbox/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(inbox)}));
  await page.route('**/api/today-layout/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,revision:0,widgets:widgetIds.map(id=>({id,visible:true,size:'full'}))})}));
  await page.route('**/api/actions/**',route=>{const results=[taskAction(task),routineAction(routine)];return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:results.length,next:null,previous:null,results,ranking_version:'actions-v1',scope:'today'})})});
  await page.route('**/api/tasks/home-task/toggle/',route=>{task.completed_at=task.completed_at?null:new Date().toISOString();dashboard.tasks=task.completed_at?[]:[task];return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(task)})});
  await page.goto('/');await page.waitForLoadState('networkidle');
  return {dashboard,inbox,state};
}

test('Today reference structure uses real family, week, weather, alerts and direct To-do actions',async({page})=>{
  await bootReference(page);
  await expect(page.getByRole('heading',{name:/Musterfamilie/})).toBeVisible();
  await expect(page.locator('.today-week li')).toHaveCount(7);
  await expect(page.locator('.today-week [aria-current="date"]')).toHaveCount(1);
  await expect(page.getByTestId('current-weather')).toContainText('17 °C');
  await expect(page.getByTestId('today-focus')).toContainText('Sturmwarnung');
  const todo=page.getByTestId('today-todos');
  await expect(todo.getByText('Paket abholen',{exact:true})).toBeVisible();
  await todo.getByRole('button',{name:'Erledigen: Paket abholen'}).click();
  await expect(todo.getByRole('button',{name:'Wieder öffnen: Paket abholen'})).toBeVisible();
  await todo.getByRole('button',{name:/Aufgabe hinzufügen|Add task/}).click();
  await expect(page.getByRole('dialog').getByRole('heading',{name:/Aufgabe hinzufügen|Add task/})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator('[data-today-widget="shopping"]').getByRole('button',{name:/Artikel hinzufügen|Add item/}).click();
  await expect(page.getByRole('dialog').getByRole('textbox',{name:/Artikel|Item/,exact:true})).toBeFocused();
});

test('Today customize action is integrated in the hero and stays usable across viewports',async({page})=>{
  await bootReference(page,{width:390,height:844});
  const hero=page.locator('.today-hero');
  const action=hero.getByTestId('today-layout-edit');
  await expect(action).toBeVisible();
  await expect(action).toHaveAccessibleName(/Anpassen|Customize/);
  await expect(page.locator('.today-layout-toolbar')).toHaveCount(0);

  for(const width of [320,390,900]){
    await page.setViewportSize({width,height:900});
    const metrics=await page.evaluate(()=>{
      const button=document.querySelector('[data-testid="today-layout-edit"]');
      const greeting=document.querySelector('.today-hero-heading-row .today-greeting');
      const buttonBox=button.getBoundingClientRect();
      const greetingBox=greeting.getBoundingClientRect();
      const overlap=!(buttonBox.left>=greetingBox.right||buttonBox.right<=greetingBox.left||buttonBox.top>=greetingBox.bottom||buttonBox.bottom<=greetingBox.top);
      return {height:buttonBox.height,overlap,overflow:document.documentElement.scrollWidth>window.innerWidth};
    });
    expect(metrics.height).toBeGreaterThanOrEqual(44);
    expect(metrics.overlap).toBeFalsy();
    expect(metrics.overflow).toBeFalsy();
  }

  await action.click();
  await expect(page.getByRole('heading',{name:/Today anpassen|Customize Today/})).toBeFocused();
});

test('Today reference modules navigate to unified To-dos, waste calendar and concrete inbox message without overflow',async({page})=>{
  await bootReference(page,{width:390,height:844});
  const todo=page.getByTestId('today-todos');
  await expect(todo).toContainText('Pflanzen gießen');
  await expect(page.getByTestId('next-waste')).toContainText('Papiertonne');
  await expect(page.getByTestId('today-inbox')).toContainText('Bitte Brotdose mitnehmen');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await todo.getByRole('link',{name:/Alle To-dos|All to-dos/}).click();
  await expect(page).toHaveURL(/page=todo/);
  await page.goto('/');await page.waitForLoadState('networkidle');
  await page.getByTestId('next-waste').getByRole('button',{name:/Papiertonne/}).click();
  await expect(page).toHaveURL(/page=calendar/);
  await page.goto('/');await page.waitForLoadState('networkidle');
  await page.getByTestId('today-inbox').getByRole('button',{name:/Bitte Brotdose mitnehmen/}).click();
  await expect(page).toHaveURL(/page=inbox.*message=message-1/);
});

test('Today shows waste only in its widget, not again in the canonical Timeline',async({page})=>{
  const {dashboard}=await bootReference(page);
  dashboard.events.splice(0,dashboard.events.length,...dashboard.events.filter(event=>event.id!=='warn-1'));
  await page.reload();
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('today-timeline')).toContainText('Kinderarzt');
  await expect(page.getByTestId('today-timeline')).not.toContainText('Papiertonne');
  await expect(page.getByTestId('next-waste')).toContainText('Papiertonne');
  await expect(page.getByText('Papiertonne',{exact:true})).toHaveCount(1);
});
