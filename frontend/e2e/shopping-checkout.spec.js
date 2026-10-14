import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const sessionId='11111111-1111-4111-8111-111111111111';
const expenseId='22222222-2222-4222-8222-222222222222';
const linkId='33333333-3333-4333-8333-333333333333';
const now=()=>new Date().toISOString();

function activeSession(){return {id:sessionId,shopping_list:'shop-1',status:'active',started_at:now(),completed_at:null,last_activity_at:now(),started_by:{id:1,name:'Alex',avatar:'',is_self:true},completed_by:null,participants:[{id:1,name:'Alex',avatar:'',is_self:true}]}}
function completion({open=1}={}){const completedAt=now();return {session:{...activeSession(),status:'completed',completed_at:completedAt,completed_by:{id:1,name:'Alex',avatar:'',is_self:true},participants:[]},completion:{version:1,shopping_list:{id:'shop-1',name:'Supermarkt',store:'Markt'},purchased_items:[{id:'density-0',name:'Artikel 1',quantity:'2×',category:'Kategorie 1',aisle:'',note:'',checked_at:completedAt}],open_items:open?[{id:'density-1',name:'Artikel 2',quantity:'2×',category:'Kategorie 2',aisle:'',note:'',checked_at:null}]:[],purchased_count:1,open_count:open,open_items_policy:'keep',completed_at:completedAt,completed_by:1},context_ref:{type:'shopping_session',id:sessionId}}}

async function bootCheckout(page,{count=2,onRoutes=null}={}){
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.shoppingLists[0].items=Array.from({length:count},(_,index)=>({id:`density-${index}`,shopping_list:'shop-1',name:`Artikel ${index+1}`,quantity:'2×',category:`Kategorie ${index+1}`,aisle:'',note:'',favorite:false,checked:false,position:(index+1)*1000}));
 let startCalls=0;let completeCalls=[];let historyPayload=completion({open:Math.max(0,count-1)});
 await page.route('**/api/shopping-sessions/start/',route=>{startCalls+=1;return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[],created:true})})});
 await page.route('**/api/shopping-sessions/current/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[]})}));
 await page.route('**/api/shopping-sessions/complete/',async route=>{const body=route.request().postDataJSON();completeCalls.push(body);historyPayload={...completion({open:Math.max(0,count-1)}),completion:{...completion({open:Math.max(0,count-1)}).completion,open_items_policy:body.open_items}};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(historyPayload)})});
 await page.route(`**/api/shopping-sessions/${sessionId}/`,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(historyPayload)}));
 if(onRoutes)await onRoutes({page,state});
 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.store-focus')).toBeVisible();
 await expect(page.getByText('Einkauf läuft',{exact:true})).toBeVisible();
 return {state,get startCalls(){return startCalls},completeCalls};
}

test('checkout · explicit finish keeps open items and reload reopens immutable session summary',async({page})=>{
 const run=await bootCheckout(page,{count:2});
 await page.locator('.store-row').filter({hasText:'Artikel 1'}).locator('.store-check').click();
 await expect(page.getByRole('button',{name:'1 im Wagen'})).toBeVisible();
 await page.getByRole('button',{name:'Einkauf abschließen'}).click();
 const openDialog=page.getByRole('dialog');
 await expect(openDialog.getByRole('heading',{name:'Noch 1 offen'})).toBeVisible();
 await openDialog.getByRole('button',{name:'Abbrechen'}).last().click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 expect(run.completeCalls).toHaveLength(0);

 await page.getByRole('button',{name:'Einkauf abschließen'}).click();
 await page.getByRole('button',{name:'Offene Artikel behalten'}).click();
 await expect(page.getByRole('heading',{name:'Einkauf abgeschlossen'})).toBeVisible();
 await expect(page.getByText('1 gekauft · 1 offen',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Beleg scannen'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Betrag eingeben'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Ohne Ausgabe abschließen'})).toBeVisible();
 expect(run.completeCalls).toEqual([{shopping_list:'shop-1',session:sessionId,open_items:'keep'}]);
 expect(new URL(page.url()).searchParams.get('session')).toBe(sessionId);

 await page.getByRole('button',{name:'Ohne Ausgabe abschließen'}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 const startsBeforeReload=run.startCalls;
 await page.reload();
 await expect(page.getByRole('heading',{name:'Einkauf abgeschlossen'})).toBeVisible();
 await expect(page.getByText('1 gekauft · 1 offen',{exact:true})).toBeVisible();
 expect(run.startCalls).toBe(startsBeforeReload);
 await page.getByRole('button',{name:'Fertig'}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect.poll(()=>new URL(page.url()).searchParams.get('session')).toBeNull();
 await expect.poll(()=>run.startCalls).toBeGreaterThan(startsBeforeReload);
});

test('checkout · amount handoff keeps finance participants explicit and linked expense survives reload',async({page})=>{
 let linked=null;let expensePayload=null;let savedExpense=null;
 const run=await bootCheckout(page,{count:1,onRoutes:async({page,state})=>{
  await page.route('**/api/families/family-1/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(state.family)}));
  await page.route('**/api/shopping-lists/shop-1/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(state.shoppingLists[0])}));
  await page.route('**/api/expenses/',async route=>{
   if(route.request().method()!=='POST')return route.fallback();
   expensePayload=route.request().postDataJSON();
   savedExpense={id:expenseId,...expensePayload,total_amount:expensePayload.total_amount,currency:expensePayload.currency||'EUR',source:'manual',status:'posted'};
   return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify(savedExpense)});
  });
  await page.route(new RegExp(`/api/expenses/${expenseId}/(?:\\?.*)?$`),route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(savedExpense)}));
  await page.route(/\/api\/context-links\/(?:\?.*)?$/,async route=>{
   if(route.request().method()==='POST'){
    linked=route.request().postDataJSON();
    return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({created:true,link:{id:linkId}})});
   }
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:savedExpense?1:0,results:savedExpense?[{id:linkId,relation:'context',source:{type:'expense',id:expenseId,lifecycle:'available',deep_link:`/?page=expenses&expense=${expenseId}`},context:{type:'shopping_session',id:sessionId,lifecycle:'completed',deep_link:`/?page=shopping&list=shop-1&mode=store&session=${sessionId}`}}]:[]})});
  });
 }});
 await page.locator('.store-check').first().click();
 await page.getByRole('button',{name:'Einkauf abschließen'}).click();
 await expect(page.getByRole('heading',{name:'Einkauf abgeschlossen'})).toBeVisible();
 await page.getByRole('button',{name:'Betrag eingeben'}).click();
 const expenseDialog=page.getByRole('dialog');
 await expect(expenseDialog.getByRole('heading',{name:/Ausgabe/})).toBeVisible();
 await expect(expenseDialog.getByText(/Alex.*Sam|Sam.*Alex/)).toBeVisible();
 await expect(expenseDialog.getByLabel('Optionaler Titel')).toHaveValue('Markt');
 await expenseDialog.getByLabel('Betrag').fill('43,27');
 await expenseDialog.getByRole('button',{name:/Speichern/}).click();
 await expect(page.getByRole('heading',{name:'Einkauf abgeschlossen'})).toBeVisible();
 await expect(page.getByText(/43,27/)).toBeVisible();
 expect(expensePayload.title).toBe('Markt');
 expect(expensePayload.participants.map(String).sort()).toEqual(['member-1','member-2'].sort());
 expect(linked).toEqual({family:'family-1',source:{type:'expense',id:expenseId},context:{type:'shopping_session',id:sessionId},relation:'context'});
 expect(run.completeCalls).toHaveLength(1);

 await page.getByRole('button',{name:'Fertig'}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await page.reload();
 await expect(page.getByRole('heading',{name:'Einkauf abgeschlossen'})).toBeVisible();
 await expect(page.getByText(/43,27/)).toBeVisible();
});
