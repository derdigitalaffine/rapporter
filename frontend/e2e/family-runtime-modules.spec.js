import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('app shell runtime feeds Today and global create without duplicate bootstrap requests',async({page})=>{
 const counts={baby:0,pets:0,session:0,inbox:0};
 page.on('request',request=>{
  const url=new URL(request.url());
  if(url.pathname==='/api/baby/module/')counts.baby+=1;
  if(url.pathname==='/api/pets/module/')counts.pets+=1;
  if(url.pathname==='/api/auth/session/')counts.session+=1;
  if(url.pathname==='/api/inbox/')counts.inbox+=1;
 });
 await installApiMocks(page,{dismissOnboarding:true});
 await page.goto('/');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.today-hero h1')).toBeVisible();
 await expect(page.locator('.global-create-fab')).toBeVisible();
 expect(counts).toEqual({baby:1,pets:1,session:1,inbox:1});
});

test('latest family load wins when an older dashboard response finishes late',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true});
 await page.addInitScript(()=>localStorage.setItem('famuhle-active-family','family-1'));
 const tasks=[
  {id:'task-a',family:'family-1',task_list:'tasks-family-1',title:'Aufgabe A',notes:'',priority:'normal',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:null,completed_at:null},
  {id:'task-b',family:'family-1',task_list:'tasks-family-1',title:'Aufgabe B',notes:'',priority:'normal',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:null,completed_at:null},
 ];
 const smartList={id:'tasks-family-1',family:'family-1',name:'Alltag',icon:'list-check',archived:false,sort_order:0,open_count:2,done_count:0};
 const dashboard=list=>({tasks:[],task_lists:[list],events:[],routines:[],shopping_lists:[],inbox_count:0,automation_count:0});
 const initialList={...smartList,id:'initial-list',name:'Ausgangsliste'};
 const staleList={...smartList,id:'stale-list',name:'Veraltete Liste'};
 const latestList={...smartList,id:'latest-list',name:'Neueste Liste'};
 let dashboardCalls=0;
 let releaseStale;
 const stalePending=new Promise(resolve=>{releaseStale=resolve});
 await page.route('**/api/task-lists/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([smartList])}));
 await page.route('**/api/tasks/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(tasks)}));
 await page.route('**/api/tasks/*/toggle/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})}));
 await page.route('**/api/dashboard/?family=family-1',async route=>{
  dashboardCalls+=1;
  if(dashboardCalls===1)return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard(initialList))});
  if(dashboardCalls===2){
   await stalePending;
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard(staleList))});
  }
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard(latestList))});
 });
 await page.goto('/?page=tasks');
 const row=title=>page.locator('.smart-row').filter({hasText:title});
 await expect(row('Aufgabe A')).toBeVisible();
 await expect(row('Aufgabe B')).toBeVisible();
 await row('Aufgabe A').locator('.smart-check').click();
 await expect.poll(()=>dashboardCalls).toBe(2);
 await row('Aufgabe B').locator('.smart-check').click();
 await expect.poll(()=>dashboardCalls).toBeGreaterThanOrEqual(3);
 await expect(page.locator('main .loading')).toHaveCount(0);
 await page.locator('.bottom-nav').getByRole('button',{name:'To-dos',exact:true}).click();
 await page.locator('.todo-tabs').getByRole('button',{name:'Listen',exact:true}).click();
 await expect(page.getByRole('link',{name:/Neueste Liste/})).toBeVisible();
 const staleResponse=page.waitForResponse(response=>{
  const url=new URL(response.url());
  return url.pathname==='/api/dashboard/'&&url.searchParams.get('family')==='family-1';
 });
 releaseStale();
 await staleResponse;
 await page.waitForLoadState('networkidle');
 await expect(page.getByRole('link',{name:/Neueste Liste/})).toBeVisible();
 await expect(page.getByRole('link',{name:/Veraltete Liste/})).toHaveCount(0);
});
