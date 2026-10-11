import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const trip={
 id:'trip-1',family:'family-1',title:'Japan',destination:'Tokyo',stage:'planning',date_precision:'season',date_year:2028,date_month:null,date_season:'autumn',starts_on:null,ends_on:null,notes:'',archived:false,participants:[],created_by:1,creator_name:'Alex',calendar_event_id:null,photos:[],can_manage:true,can_add_photos:true,created_at:'2026-10-10T20:00:00.000Z',updated_at:'2026-10-10T22:00:00.000Z',
};
const defaultLedger={id:'ledger-default',family:'family-1',name:'Familie – laufend',base_currency:'EUR',budget_amount:null,is_default:true,archived:false};
const tripLedger={id:'ledger-trip',family:'family-1',name:'Japan',base_currency:'EUR',budget_amount:null,is_default:false,archived:false};

async function installTravelExpenseApi(page){
 await installApiMocks(page,{dismissOnboarding:true});
 const store={tripLedger:null,createCalls:0};
 await page.route('**/api/trips/**',route=>{
  const request=route.request();const url=new URL(request.url());
  if(url.pathname==='/api/trips/'&&request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([trip])});
  return route.fallback();
 });
 await page.route('**/api/expense-ledgers/**',async route=>{
  const request=route.request();const url=new URL(request.url());
  if(url.pathname==='/api/expense-ledgers/for-trip/'&&request.method()==='GET'){
   if(!store.tripLedger)return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({code:'trip_expense_ledger_unavailable'})});
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(store.tripLedger)});
  }
  if(url.pathname==='/api/expense-ledgers/for-trip/'&&request.method()==='POST'){
   store.createCalls+=1;store.tripLedger={...tripLedger};
   return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify(store.tripLedger)});
  }
  if(url.pathname==='/api/expense-ledgers/'&&request.method()==='GET'){
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(store.tripLedger?[defaultLedger,store.tripLedger]:[defaultLedger])});
  }
  return route.fallback();
 });
 await page.route('**/api/expenses/**',route=>{
  const request=route.request();const url=new URL(request.url());
  if(url.pathname==='/api/expenses/'&&request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:'[]'});
  if(url.pathname==='/api/expenses/balance/'&&request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({family:'family-1',ledger:'ledger-trip',currency:'EUR',open_amount:'0.00',members:[]})});
  if(url.pathname==='/api/expenses/settlement-plan/'&&request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({family:'family-1',ledger:'ledger-trip',currency:'EUR',transfers:[],disclaimer:''})});
  if(url.pathname==='/api/expenses/settlements/'&&request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:'[]'});
  return route.fallback();
 });
 return store;
}

async function openTrip(page){
 await page.goto('/?page=trips');
 await expect(page.getByRole('heading',{name:'Reisen',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Öffnen',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Japan',exact:true})).toBeVisible();
}

test('travel · trip expenses create one canonical ledger and reopen the same ledger',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const store=await installTravelExpenseApi(page);
 await openTrip(page);

 await page.getByRole('button',{name:'Reisekosten',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Ausgaben',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/page=expenses.*ledger=ledger-trip/);
 await expect(page.getByLabel('Abrechnungskreis')).toHaveValue('ledger-trip');
 await expect(page.locator('.balance-card-head').getByText('Japan',{exact:true})).toBeVisible();
 expect(store.createCalls).toBe(1);

 await page.goBack();
 await expect(page.getByRole('heading',{name:'Reisen',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Öffnen',exact:true}).click();
 await page.getByRole('button',{name:'Reisekosten',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Ausgaben',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/ledger=ledger-trip/);
 expect(store.createCalls).toBe(1);
});
