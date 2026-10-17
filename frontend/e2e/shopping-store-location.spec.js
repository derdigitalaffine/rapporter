import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const sessionId='55555555-5555-4555-8555-555555555555';
const storeId='66666666-6666-4666-8666-666666666666';
const now=()=>new Date().toISOString();

function activeSession(){return {id:sessionId,shopping_list:'shop-1',status:'active',started_at:now(),completed_at:null,last_activity_at:now(),started_by:{id:1,name:'Alex',avatar:'',is_self:true},completed_by:null,participants:[{id:1,name:'Alex',avatar:'',is_self:true}]}}

test('checkout · typing stays local and explicit search resolves canonical store',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.shoppingLists[0].items=[{id:'location-1',shopping_list:'shop-1',name:'Milch',quantity:'',category:'',aisle:'',note:'',favorite:false,checked:false,position:1000}];
 let lookupCalls=0;let resolveCalls=0;const completeCalls=[];
 const candidate={provider:'nominatim',provider_ref:'12345',name:'Markt',branch_label:'Innenstadt',address:'Marktstraße 1',latitude:'49.443100',longitude:'7.768900',display_label:'Markt · Innenstadt'};
 const store={id:storeId,family:'family-1',name:'Markt',branch_label:'Innenstadt',address:'Marktstraße 1',display_label:'Markt · Innenstadt',active:true,shopping_list_ids:['shop-1']};
 await page.route('**/api/shopping-sessions/start/',route=>route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[],created:true})}));
 await page.route('**/api/shopping-sessions/current/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[]})}));
 await page.route('**/api/shopping-stores/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:0,results:[]})}));
 await page.route('**/api/shopping-store-locations/resolve/',async route=>{resolveCalls+=1;return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({store,created:true})})});
 await page.route(/\/api\/shopping-store-locations\/\?.*$/,route=>{lookupCalls+=1;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({results:[candidate],attribution:'© OpenStreetMap contributors'})})});
 await page.route('**/api/shopping-sessions/complete/',async route=>{const body=route.request().postDataJSON();completeCalls.push(body);const completedAt=now();return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session:{...activeSession(),status:'completed',completed_at:completedAt,completed_by:{id:1,name:'Alex',avatar:'',is_self:true},participants:[]},completion:{version:1,shopping_list:{id:'shop-1',name:'Supermarkt',store:'Markt · Innenstadt'},confirmed_store:store,purchased_items:[{id:'location-1',name:'Milch',checked_at:completedAt}],open_items:[],purchased_count:1,open_count:0,open_items_policy:'keep',completed_at:completedAt,completed_by:1},context_ref:{type:'shopping_session',id:sessionId}})})});

 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await page.locator('.store-check').first().click();
 await page.getByRole('button',{name:'Einkauf abschließen'}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByText('Andere Filiale suchen',{exact:true}).click();
 const query=dialog.getByLabel('Geschäft oder Adresse');
 await query.fill('Markt');
 await page.waitForTimeout(250);
 expect(lookupCalls).toBe(0);

 await dialog.getByRole('button',{name:'Suchen'}).click();
 await expect.poll(()=>lookupCalls).toBe(1);
 await expect(dialog.getByText('© OpenStreetMap contributors')).toBeVisible();
 await dialog.getByRole('button',{name:/Markt · Innenstadt/}).click();
 await expect.poll(()=>resolveCalls).toBe(1);
 await expect(dialog.getByLabel('Filiale (optional)')).toHaveValue(storeId);

 await dialog.getByRole('button',{name:'Einkauf abschließen'}).click();
 await expect(page.getByRole('heading',{name:'Einkauf abgeschlossen'})).toBeVisible();
 expect(completeCalls).toEqual([{shopping_list:'shop-1',session:sessionId,open_items:'keep',store:storeId}]);
});
