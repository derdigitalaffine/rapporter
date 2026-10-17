import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const sessionId='55555555-5555-4555-8555-555555555555';
const now=()=>new Date().toISOString();

function session({peers=true,revision=4,status='active'}={}){
 const participants=[{id:1,name:'Alex',avatar:'',is_self:true}];
 if(peers)participants.push({id:2,name:'Sam',avatar:'',is_self:false});
 return {id:sessionId,shopping_list:'shop-1',status,revision,started_at:now(),completed_at:status==='completed'?now():null,last_activity_at:now(),started_by:{id:1,name:'Alex',avatar:'',is_self:true},completed_by:status==='completed'?{id:1,name:'Alex',avatar:'',is_self:true}:null,participants:status==='completed'?[]:participants};
}

function completion(){
 const completedAt=now();
 return {session:{...session({peers:false,status:'completed'}),completed_at:completedAt},completion:{version:1,shopping_list:{id:'shop-1',name:'Supermarkt',store:''},confirmed_store:null,purchased_items:[{id:'collab-1',name:'Milch',quantity:'1×',category:'Milchprodukte',aisle:'',note:'',checked_at:completedAt}],open_items:[],purchased_count:1,open_count:0,open_items_policy:'keep',completed_at:completedAt,completed_by:1},context_ref:{type:'shopping_session',id:sessionId}};
}

async function boot(page){
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.shoppingLists[0].items=[{id:'collab-1',shopping_list:'shop-1',name:'Milch',quantity:'1×',category:'Milchprodukte',aisle:'',note:'',favorite:false,checked:false,position:1000}];
 const completeBodies=[];
 await page.route('**/api/shopping-sessions/start/',route=>route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({session:session(),cursor:4,activities:[],created:true})}));
 await page.route('**/api/shopping-sessions/current/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session:session(),cursor:4,activities:[]})}));
 await page.route('**/api/shopping-stores/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:0,results:[]})}));
 await page.route('**/api/shopping-sessions/complete/',async route=>{
  const body=route.request().postDataJSON();completeBodies.push(body);
  if(body.scope==='me')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({left:true,session:session({peers:false})})});
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(completion())});
 });
 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.store-focus')).toBeVisible();
 await page.locator('.store-check').first().click();
 await page.getByRole('button',{name:'Einkauf abschließen'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByText('Gemeinsamer Einkauf',{exact:true})).toBeVisible();
 await expect(dialog.getByText(/Sam/)).toBeVisible();
 return {dialog,completeBodies};
}

test('checkout · personal finish leaves the shared session without closing it',async({page})=>{
 const run=await boot(page);
 await run.dialog.getByRole('button',{name:'Mein Einkauf beendet'}).click();
 await expect(page.locator('.store-focus')).toHaveCount(0);
 expect(run.completeBodies).toEqual([{shopping_list:'shop-1',session:sessionId,scope:'me'}]);
});

test('checkout · active peers require explicit group confirmation and frozen revision',async({page})=>{
 const run=await boot(page);
 const finish=run.dialog.getByRole('button',{name:'Einkauf abschließen'});
 await expect(finish).toBeDisabled();
 await run.dialog.getByLabel('Gemeinsamen Einkauf jetzt abschließen').check();
 await expect(finish).toBeEnabled();
 await finish.click();
 await expect(page.getByRole('heading',{name:'Einkauf abgeschlossen'})).toBeVisible();
 expect(run.completeBodies).toEqual([{shopping_list:'shop-1',session:sessionId,open_items:'keep',store:null,expected_revision:4,confirm_active_peers:true}]);
});
