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
 const families=[
  {id:'family-1',name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-1',family:'family-1',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''}]},
  {id:'family-2',name:'Zweitfamilie',slug:'zweitfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-2',family:'family-2',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''}]},
 ];
 const dashboard=family=>({tasks:[{id:`task-${family}`,family,title:family==='family-1'?'Aufgabe Familie Eins':'Aufgabe Familie Zwei',completed_at:null,priority:'normal'}],task_lists:[],events:[],routines:[],shopping_lists:[],inbox_count:0,automation_count:0});
 let releaseFamilyTwo;
 const familyTwoPending=new Promise(resolve=>{releaseFamilyTwo=resolve});
 await page.route('**/api/families/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(families)}));
 await page.route('**/api/dashboard/?family=family-1',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard('family-1'))}));
 await page.route('**/api/dashboard/?family=family-2',async route=>{await familyTwoPending;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboard('family-2'))})});
 await page.goto('/');
 await expect(page.getByText('Aufgabe Familie Eins')).toBeVisible();
 const switcher=page.locator('.family-switcher select');
 await switcher.selectOption('family-2');
 await switcher.evaluate(element=>{element.value='family-1';element.dispatchEvent(new Event('change',{bubbles:true}))});
 await expect(page.getByText('Aufgabe Familie Eins')).toBeVisible();
 releaseFamilyTwo();
 await page.waitForTimeout(100);
 await expect(switcher).toHaveValue('family-1');
 await expect(page.getByText('Aufgabe Familie Eins')).toBeVisible();
 await expect(page.getByText('Aufgabe Familie Zwei')).toHaveCount(0);
});
