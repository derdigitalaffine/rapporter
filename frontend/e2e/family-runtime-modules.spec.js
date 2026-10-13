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
 const families=[
  {id:'family-1',name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-1',family:'family-1',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''}]},
  {id:'family-2',name:'Zweitfamilie',slug:'zweitfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-2',family:'family-2',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''}]},
 ];
 const taskFor=family=>({id:`task-${family}`,family,task_list:`tasks-${family}`,title:family==='family-1'?'Aufgabe Familie Eins':'Aufgabe Familie Zwei',notes:'',priority:'normal',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:null,completed_at:null});
 const dashboard=family=>({tasks:[taskFor(family)],task_lists:[{id:`tasks-${family}`,family,name:'Alltag',icon:'list-check',archived:false,sort_order:0,open_count:1,done_count:0}],events:[],routines:[],shopping_lists:[],inbox_count:0,automation_count:0});
 const actions=family=>{const task=taskFor(family);const primary={id:'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`};return {count:1,next:null,previous:null,ranking_version:'actions-v1',scope:'today',results:[{id:`task:${task.id}`,family,kind:'task',title:task.title,state:'open',due_at:null,next_due_at:null,completed_at:null,assignee:{id:1,username:'Alex'},priority:'normal',urgency:'normal',context:{source:'manual',list:{id:task.task_list,name:task.list_name},workflow:null},repeat:null,tags:[],primary_action:primary,allowed_actions:[primary],deep_link:`/?page=tasks&task=${task.id}`,ranking:{version:'actions-v1',bucket:5,reasons:['normal']}}]}};
 let releaseFamilyTwo;
 const familyTwoPending=new Promise(resolve=>{releaseFamilyTwo=resolve});
 await page.route('**/api/families/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(families)}));
 await page.route('**/api/dashboard/?family=family-1',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard('family-1'))}));
 await page.route('**/api/dashboard/?family=family-2',async route=>{await familyTwoPending;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard('family-2'))})});
 await page.route('**/api/actions/**',route=>{const family=new URL(route.request().url()).searchParams.get('family')||'family-1';return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(actions(family))})});
 await page.goto('/');
 const switcher=page.locator('.family-switcher select');
 const todos=page.getByTestId('today-todos');
 await expect(switcher).toHaveValue('family-1');
 await expect(todos.getByText('Aufgabe Familie Eins',{exact:true})).toBeVisible();
 await switcher.selectOption('family-2');
 await expect(switcher).toHaveValue('family-2');
 await switcher.selectOption('family-1');
 await expect(switcher).toHaveValue('family-1');
 await expect(todos.getByText('Aufgabe Familie Eins',{exact:true})).toBeVisible();
 releaseFamilyTwo();
 await expect(switcher).toHaveValue('family-1');
 await expect(todos.getByText('Aufgabe Familie Eins',{exact:true})).toBeVisible();
 await expect(todos.getByText('Aufgabe Familie Zwei',{exact:true})).toHaveCount(0);
});
