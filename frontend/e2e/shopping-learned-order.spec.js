import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const sessionId='77777777-7777-4777-8777-777777777777';
const storeId='88888888-8888-4888-8888-888888888888';
const orderModeKey=`famuhle-shopping-order-mode:family-1:store-${storeId}`;
const now=()=>new Date().toISOString();
const activeSession=()=>({id:sessionId,shopping_list:'shop-1',status:'active',started_at:now(),completed_at:null,last_activity_at:now(),started_by:{id:1,name:'Alex',avatar:'',is_self:true},completed_by:null,participants:[{id:1,name:'Alex',avatar:'',is_self:true}]});
const learnedPayload=orderedItems=>({store:storeId,source:'learned',confidence:1,evidence:{streams:2,pair_observations:4},ordered_items:orderedItems});

async function routeSession(page){
 await page.route('**/api/shopping-sessions/start/',route=>route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[],created:true})}));
 await page.route('**/api/shopping-sessions/current/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[]})}));
}

async function selectLearnedByDefault(page){
 await page.addInitScript(key=>localStorage.setItem(key,'learned'),orderModeKey);
}

test('store mode applies explicitly selected learned order and sends client-local sequence',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});
 await selectLearnedByDefault(page);
 state.shoppingLists[0].items=[
  {id:'item-milk',shopping_list:'shop-1',name:'Milk',quantity:'',category:'',aisle:'',note:'',favorite:false,checked:false,position:10},
  {id:'item-bread',shopping_list:'shop-1',name:'Bread',quantity:'',category:'',aisle:'',note:'',favorite:false,checked:false,position:20},
  {id:'item-apples',shopping_list:'shop-1',name:'Apples',quantity:'',category:'',aisle:'',note:'',favorite:false,checked:false,position:30},
 ];
 const store={id:storeId,family:'family-1',name:'Market',branch_label:'Downtown',display_label:'Market · Downtown',active:true,shopping_list_ids:['shop-1']};
 const patches=[];
 await routeSession(page);
 await page.route('**/api/shopping-stores/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:1,results:[store]})}));
 await page.route(`**/api/shopping-stores/${storeId}/learned-order/**`,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(learnedPayload([{id:'item-apples',name:'Apples',key:'apples'},{id:'item-bread',name:'Bread',key:'bread'},{id:'item-milk',name:'Milk',key:'milk'}]))}));
 await page.route('**/api/shopping-items/item-apples/',async route=>{const body=route.request().postDataJSON();patches.push(body);return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...state.shoppingLists[0].items[2],checked:true,checked_at:now()})})});

 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await expect(page.getByLabel('Sortierung im Laden')).toHaveValue('learned');
 await expect.poll(async()=>page.locator('.store-row strong').allTextContents()).toEqual(['Apples','Bread','Milk']);
 await page.locator('.store-check').first().click();
 await expect.poll(()=>patches.length).toBe(1);
 expect(patches[0].checked).toBe(true);
 expect(patches[0].client_activity.stream).toBeTruthy();
 expect(patches[0].client_activity.sequence).toBe(1);
 expect(patches[0].client_activity.mutation_id).toBeTruthy();
 expect(patches[0]).not.toHaveProperty('latitude');
 expect(patches[0]).not.toHaveProperty('longitude');
});

test('store mode defaults to categories and does not fetch learned order without opt-in',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.shoppingLists[0].items=[
  {id:'fallback-b',shopping_list:'shop-1',name:'B',quantity:'',category:'Other',aisle:'',note:'',favorite:false,checked:false,position:20},
  {id:'fallback-a',shopping_list:'shop-1',name:'A',quantity:'',category:'Other',aisle:'',note:'',favorite:false,checked:false,position:10},
 ];
 const store={id:storeId,family:'family-1',name:'Market',display_label:'Market',active:true,shopping_list_ids:['shop-1']};
 let learnedRequests=0;
 await routeSession(page);
 await page.route('**/api/shopping-stores/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:1,results:[store]})}));
 await page.route(`**/api/shopping-stores/${storeId}/learned-order/**`,route=>{learnedRequests+=1;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(learnedPayload([{id:'fallback-b',name:'B'},{id:'fallback-a',name:'A'}]))})});

 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await expect(page.getByLabel('Sortierung im Laden')).toHaveValue('categories');
 await expect.poll(async()=>page.locator('.store-row strong').allTextContents()).toEqual(['A','B']);
 expect(learnedRequests).toBe(0);
});

test('changing order mode never reorders the running trip and applies on the next start',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.shoppingLists[0].items=[
  {id:'item-a',shopping_list:'shop-1',name:'A',quantity:'',category:'Other',aisle:'',note:'',favorite:false,checked:false,position:10},
  {id:'item-b',shopping_list:'shop-1',name:'B',quantity:'',category:'Other',aisle:'',note:'',favorite:false,checked:false,position:20},
 ];
 const store={id:storeId,family:'family-1',name:'Market',display_label:'Market',active:true,shopping_list_ids:['shop-1']};
 await routeSession(page);
 await page.route('**/api/shopping-stores/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:1,results:[store]})}));
 await page.route(`**/api/shopping-stores/${storeId}/learned-order/**`,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(learnedPayload([{id:'item-b',name:'B'},{id:'item-a',name:'A'}]))}));

 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await expect.poll(async()=>page.locator('.store-row strong').allTextContents()).toEqual(['A','B']);

 await page.getByLabel('Sortierung im Laden').selectOption('learned');
 await expect(page.getByLabel('Sortierung im Laden')).toHaveValue('learned');
 await expect.poll(async()=>page.locator('.store-row strong').allTextContents()).toEqual(['A','B']);
 await expect.poll(()=>page.evaluate(key=>localStorage.getItem(key),orderModeKey)).toBe('learned');

 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect(page.getByLabel('Sortierung im Laden')).toHaveValue('learned');
 await expect.poll(async()=>page.locator('.store-row strong').allTextContents()).toEqual(['B','A']);
});
