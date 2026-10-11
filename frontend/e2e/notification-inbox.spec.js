import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

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
