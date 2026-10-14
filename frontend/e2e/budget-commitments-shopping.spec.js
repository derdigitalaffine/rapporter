import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

test('finance · reserved shopping item opens the existing expense flow instead of auto-posting',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true,language:'de'});
 const ledger={id:'ledger-home',family:'family-1',name:'Familie',base_currency:'EUR',budget_amount:'500.00',estimated_amount:null,is_default:true,archived:false};
 const budget={id:'budget-food',family:'family-1',ledger:'ledger-home',name:'Lebensmittel',amount:'300.00',estimated_amount:null,spent_amount:'0.00',remaining_amount:'300.00',archived:false};
 let commitment=null;
 let checkedWrites=0;

 await page.route(/\/api\/expense-ledgers\/(?:\?.*)?$/,async route=>{
  if(route.request().method()==='GET')return json(route,[ledger]);
  return route.fallback();
 });
 await page.route(/\/api\/expense-budgets\/(?:\?.*)?$/,async route=>{
  if(route.request().method()==='GET')return json(route,[budget]);
  return route.fallback();
 });
 await page.route(/\/api\/budget-commitments\/source\/shopping_item\/item-1\/(?:\?.*)?$/,async route=>{
  const method=route.request().method();
  if(method==='GET')return json(route,{commitment});
  if(method==='PUT'){
   const body=route.request().postDataJSON();
   commitment={id:'commitment-1',family:'family-1',ledger:body.ledger,budget:body.budget,source_type:'shopping_item',source_id:'item-1',amount:Number(body.amount).toFixed(2),currency:'EUR',status:'active'};
   return json(route,{commitment});
  }
  if(method==='DELETE'){commitment=null;return json(route,{commitment:null})}
  return route.fallback();
 });
 await page.route(/\/api\/shopping-items\/item-1\/(?:\?.*)?$/,async route=>{
  const method=route.request().method();
  const item=state.shoppingLists[0].items.find(row=>row.id==='item-1');
  if(method==='GET')return json(route,item);
  if(method==='PATCH'){
   const body=route.request().postDataJSON();
   if(body.checked===true)checkedWrites+=1;
   Object.assign(item,body);return json(route,item);
  }
  return route.fallback();
 });

 await page.setViewportSize({width:390,height:844});
 await page.goto('/?page=shopping');
 await page.waitForLoadState('networkidle');

 const panel=page.locator('details.shopping-budget-commitment');
 await panel.locator('summary').click();
 await panel.getByLabel('Budgettopf').selectOption('budget-food');
 await panel.getByLabel(/Vorgemerkt/).fill('75,50');
 await panel.getByRole('button',{name:'Vormerken',exact:true}).click();
 await expect(panel).toContainText('75.50 EUR vorgemerkt');

 await page.getByRole('button',{name:/Milch.*Erledigen/}).click();
 const dialog=page.getByRole('dialog',{name:'Ausgabe hinzufügen'});
 await expect(dialog).toBeVisible();
 await expect(dialog.getByLabel('Betrag')).toHaveValue('75.50');
 await expect(dialog.getByLabel('Händler / Titel')).toHaveValue('Milch');
 await expect(dialog.getByLabel('Konto')).toHaveValue('ledger-home');
 await expect(dialog.getByLabel('Budgettopf (optional)')).toHaveValue('budget-food');
 expect(checkedWrites).toBe(0);
});
