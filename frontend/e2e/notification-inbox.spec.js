import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function expectMinTarget(locator){const box=await locator.boundingBox();expect(box?.width).toBeGreaterThanOrEqual(44);expect(box?.height).toBeGreaterThanOrEqual(44)}

test('in-app notification inbox renders unread activity and marks all read',async({page})=>{
 await installApiMocks(page,{language:'de'});
 const rows=[{
  id:'notification-1',family:'family-1',event_type:'task.created',title:'Neue Aufgabe',body:'Sam hat „Müll rausbringen“ zu Haushalt hinzugefügt.',resource_url:'',priority:'normal',read:false,read_at:null,created_at:new Date().toISOString(),
 }];
 let readAllCalls=0;
 await page.route('**/api/notifications/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname;
  if(request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({results:rows,unread_count:rows.filter(row=>!row.read).length,next_cursor:null,previous_cursor:null})});
  if(path.endsWith('/read-all/')&&request.method()==='POST'){
   readAllCalls+=1;for(const row of rows){row.read=true;row.read_at=new Date().toISOString()}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({updated:1,unread_count:0})});
  }
  return route.fulfill({status:404,contentType:'application/json',body:'{}'});
 });
 await page.goto('/?page=notifications');
 await expect(page.getByRole('heading',{name:'Mitteilungen'})).toBeVisible();
 await expect(page.getByText('Neue Aufgabe')).toBeVisible();
 await expect(page.getByText('1 ungelesen')).toBeVisible();
 const row=page.locator('.notification-inbox-row',{hasText:'Neue Aufgabe'});await expect(row).toHaveClass(/unread/);
 await page.getByRole('button',{name:/Alle als gelesen markieren/}).click();
 await expect.poll(()=>readAllCalls).toBe(1);
 await expect(page.getByText('1 ungelesen')).toHaveCount(0);
 await expect(row).toHaveClass(/read/);
});

test('notification settings keep canonical action variants and touch targets',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await installApiMocks(page,{language:'de'});
 await page.addInitScript(()=>{
  const subscription={endpoint:'https://push.example.test/subscription',unsubscribe:async()=>true,toJSON:()=>({endpoint:'https://push.example.test/subscription'})};
  const registration={pushManager:{getSubscription:async()=>subscription,subscribe:async()=>subscription}};
  Object.defineProperty(window,'PushManager',{configurable:true,value:function PushManager(){}});
  Object.defineProperty(window,'Notification',{configurable:true,value:{permission:'granted',requestPermission:async()=>'granted'}});
  Object.defineProperty(navigator,'serviceWorker',{configurable:true,value:{ready:Promise.resolve(registration),register:async()=>registration,addEventListener:()=>{},removeEventListener:()=>{},controller:null}});
 });
 await page.route('**/api/push/config/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({configured:true,devices:1,public_key:'test'})}));
 await page.route('**/api/push/preferences/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({tasks:true,task_assigned:true,shopping:true,calendar:true,family_updates:true,messages:true,routines:true,birthdays:true,birthday_prepare:true,detail_level:'summary',quiet_hours_enabled:false,quiet_start:'22:00',quiet_end:'07:00'})}));
 await page.route('**/api/notifications/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({results:[],unread_count:0,next_cursor:null,previous_cursor:null})}));
 await page.goto('/?page=notifications');
 await expect(page.getByText('Auf diesem Gerät aktiv')).toBeVisible();

 const back=page.locator('.page-head .back-button').first();
 await expect(back).toHaveClass(/\bghost\b/);await expect(back).toHaveClass(/\bicon-button\b/);await expect(back).toHaveAttribute('type','button');await expectMinTarget(back);
 const disable=page.locator('.notification-state button.ghost-danger');
 await expect(disable).toHaveClass(/\bghost\b/);await expect(disable).toHaveClass(/\bghost-danger\b/);await expect(disable).toHaveAttribute('type','button');await expectMinTarget(disable);
 const sendTest=page.locator('.notification-state .push-actions button.primary');
 await expect(sendTest).toHaveAttribute('type','button');await expectMinTarget(sendTest);
 const rules=page.locator('.push-rules-card button');
 await expect(rules).toHaveClass(/\bprimary\b/);await expect(rules).toHaveAttribute('type','button');await expectMinTarget(rules);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
