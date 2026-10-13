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

test('latest family load wins when an older family response finishes late',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true});
 await page.addInitScript(()=>localStorage.setItem('famuhle-active-family','family-1'));
 const task=(id,title)=>({id,family:'family-1',task_list:'tasks-family-1',title,notes:'',priority:'normal',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:null,completed_at:null});
 const dashboard=tasks=>({tasks,task_lists:[{id:'tasks-family-1',family:'family-1',name:'Alltag',icon:'list-check',archived:false,sort_order:0,open_count:tasks.length,done_count:0}],events:[],routines:[],shopping_lists:[],inbox_count:0,automation_count:0});
 const initial=dashboard([task('task-a','Aufgabe A'),task('task-b','Aufgabe B')]);
 const stale=dashboard([task('task-stale','Veraltete Antwort')]);
 const latest=dashboard([task('task-latest','Neueste Antwort')]);
 let dashboardCalls=0;
 let releaseStale;
 const stalePending=new Promise(resolve=>{releaseStale=resolve});
 await page.route('**/api/dashboard/?family=family-1',async route=>{
  dashboardCalls+=1;
  if(dashboardCalls===1)return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(initial)});
  if(dashboardCalls===2){await stalePending;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(stale)})}
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(latest)});
 });
 await page.route('**/api/tasks/*/toggle/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})}));
 await page.goto('/');
 const row=title=>page.locator('.today-task-row').filter({hasText:title});
 await expect(row('Aufgabe A')).toBeVisible();
 await expect(row('Aufgabe B')).toBeVisible();
 await row('Aufgabe A').locator('.today-check').click();
 await expect.poll(()=>dashboardCalls).toBe(2);
 await row('Aufgabe B').locator('.today-check').click();
 await expect.poll(()=>dashboardCalls).toBeGreaterThanOrEqual(3);
 await expect(page.getByText('Neueste Antwort',{exact:true})).toBeVisible();
 releaseStale();
 await expect(page.getByText('Neueste Antwort',{exact:true})).toBeVisible();
 await expect(page.getByText('Veraltete Antwort',{exact:true})).toHaveCount(0);
});
