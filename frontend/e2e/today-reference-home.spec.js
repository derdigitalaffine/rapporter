import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const isoIn=hours=>new Date(Date.now()+hours*3600000).toISOString();
const widgetIds=['priority','next','weather','tasks','shopping','routines','waste','inbox','birthdays','notes','loyalty'];

async function bootReference(page,viewport={width:390,height:844}){
  await page.setViewportSize(viewport);
  await installApiMocks(page,{dismissOnboarding:true});
  const task={id:'home-task',family:'family-1',task_list:'tasks-1',title:'Paket abholen',notes:'',priority:'high',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:isoIn(2),completed_at:null};
  const dashboard={
    tasks:[task],task_lists:[{id:'tasks-1',family:'family-1',name:'Alltag',open_count:1,done_count:0}],
    shopping_lists:[{id:'shop-1',family:'family-1',name:'Supermarkt',open_count:2,checked_count:0,items:[{id:'milk',name:'Milch',quantity:'1 l',category:'Kühlung',checked:false},{id:'bread',name:'Brot',quantity:'1',category:'Backwaren',checked:false}]}],
    routines:[{id:'routine-1',family:'family-1',name:'Pflanzen gießen',active:true,last_done_at:isoIn(-20),prediction:{status:'learning'}}],
    events:[
      {id:'warn-1',family:'family-1',type:'public.warning',title:'Sturmwarnung',starts_at:isoIn(1),payload:{provider:'Warnamt'}},
      {id:'waste-1',family:'family-1',type:'waste.paper',title:'Papiertonne',starts_at:isoIn(24),payload:{provider:'Stadt'}},
      {id:'event-1',family:'family-1',type:'calendar.event',title:'Kinderarzt',starts_at:isoIn(4),payload:{location:'Praxis',provider:'FamilyOS'}}
    ],
    weather:{current:{temperature:17,apparent_temperature:16,weather_code:2,wind_speed:8,observed_at:new Date().toISOString()}},birthdays:[],inbox_count:1,automation_count:0
  };
  const inbox=[{id:'message-1',family:'family-1',status:'new',unread:true,source:'manual_message',title:'Bitte Brotdose mitnehmen',body:'Bitte Brotdose mitnehmen',created_by_name:'Sam',created_at:isoIn(-1)}];
  await page.route('**/api/dashboard/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard)}));
  await page.route('**/api/inbox/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(inbox)}));
  await page.route('**/api/today-layout/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,revision:0,widgets:widgetIds.map(id=>({id,visible:true,size:'full'}))})}));
  await page.route('**/api/tasks/home-task/toggle/',route=>{task.completed_at=new Date().toISOString();dashboard.tasks=[];return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(task)})});
  await page.goto('/');await page.waitForLoadState('networkidle');
  return {dashboard,inbox};
}

test('Today reference structure uses real family, week, weather, alerts and direct actions',async({page})=>{
  await bootReference(page);
  await expect(page.getByRole('heading',{name:/Musterfamilie/})).toBeVisible();
  const compass=page.getByTestId('week-compass');
  await expect(compass.locator('.week-compass-days li')).toHaveCount(7);
  await expect(compass.locator('[aria-current="date"]')).toHaveCount(1);
  await expect(compass.getByRole('button',{name:'Vorherige Woche'})).toBeVisible();
  await expect(compass.getByRole('button',{name:'Nächste Woche'})).toBeVisible();
  await expect(page.getByTestId('current-weather')).toContainText('17 °C');
  await expect(page.getByText('Sturmwarnung',{exact:true}).first()).toBeVisible();
  await expect(page.getByText('Paket abholen',{exact:true}).last()).toBeVisible();
  await page.locator('[data-today-widget="tasks"] .today-check').click();
  await expect(page.locator('[data-today-widget="tasks"]')).not.toContainText('Paket abholen');
  await page.locator('[data-today-widget="tasks"]').getByRole('button',{name:/Aufgabe hinzufügen|Add task/}).click();
  await expect(page.getByRole('dialog').getByRole('heading',{name:/Aufgabe hinzufügen|Add task/})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator('[data-today-widget="shopping"]').getByRole('button',{name:/Artikel hinzufügen|Add item/}).click();
  await expect(page.getByRole('dialog').getByRole('textbox',{name:/Artikel|Item/,exact:true})).toBeFocused();
});

test('Today reference modules navigate to waste calendar, routines and concrete inbox message without overflow',async({page})=>{
  await bootReference(page,{width:390,height:844});
  await expect(page.getByTestId('today-routines')).toContainText('Pflanzen gießen');
  await expect(page.getByTestId('next-waste')).toContainText('Papiertonne');
  await expect(page.getByTestId('today-inbox')).toContainText('Bitte Brotdose mitnehmen');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.getByTestId('today-routines').getByRole('button',{name:/Alle|All/}).click();
  await expect(page).toHaveURL(/page=routines/);
  await page.goto('/');await page.waitForLoadState('networkidle');
  await page.getByTestId('next-waste').getByRole('button',{name:/Papiertonne/}).click();
  await expect(page).toHaveURL(/page=calendar/);
  await page.goto('/');await page.waitForLoadState('networkidle');
  await page.getByTestId('today-inbox').getByRole('button',{name:/Bitte Brotdose mitnehmen/}).click();
  await expect(page).toHaveURL(/page=inbox.*message=message-1/);
});
