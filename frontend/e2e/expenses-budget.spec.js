import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

function expense({id,ledger='ledger-default',amount='0.00',currency='EUR',funding='member',title='Ausgabe'}){
 return {
  id,family:'family-1',ledger,title,merchant:title,occurred_at:'2026-10-09T12:00:00.000Z',total_amount:amount,currency,
  funding_source:funding,paid_by:funding==='shared'?null:'member-1',paid_by_name:funding==='shared'?null:'Alex',created_by:1,
  receipt_status:'none',receipt_available:false,source:'manual',status:'posted',notes:'',shares:funding==='shared'?[]:[
   {id:`${id}-share-1`,member:'member-1',member_name:'Alex',amount:(Number(amount)/2).toFixed(2),split_type:'equal'},
   {id:`${id}-share-2`,member:'member-2',member_name:'Sam',amount:(Number(amount)/2).toFixed(2),split_type:'equal'},
  ],extraction:null,
 };
}

async function installBudgetMocks(page){
 const store={
  expenses:[],
  ledgers:[
   {id:'ledger-default',family:'family-1',name:'Familie – laufend',base_currency:'EUR',budget_amount:'500.00',is_default:true,archived:false},
   {id:'ledger-trip',family:'family-1',name:'Urlaub',base_currency:'EUR',budget_amount:'800.00',is_default:false,archived:false},
  ],
  budgets:[
   {id:'budget-home',family:'family-1',ledger:'ledger-default',parent:null,name:'Haushalt',amount:'300.00',currency:'EUR',archived:false,spent_amount:'0.00',remaining_amount:'300.00',over_budget:false},
   {id:'budget-trip',family:'family-1',ledger:'ledger-trip',parent:null,name:'Reisebudget',amount:'800.00',currency:'EUR',archived:false,spent_amount:'0.00',remaining_amount:'800.00',over_budget:false},
  ],
 };
 const ledgerRows=ledgerId=>store.expenses.filter(item=>String(item.ledger)===String(ledgerId));
 const summary=ledgerId=>{
  const ledger=store.ledgers.find(item=>String(item.id)===String(ledgerId));
  const currency=ledger?.base_currency||'EUR';
  const rows=ledgerRows(ledgerId);
  const spent=rows.filter(item=>item.currency===currency).reduce((sum,item)=>sum+Number(item.total_amount||0),0);
  const budgetAmount=ledger?.budget_amount===null||ledger?.budget_amount===undefined?null:Number(ledger.budget_amount);
  const remaining=budgetAmount===null?null:budgetAmount-spent;
  return {
   family:'family-1',ledger:ledgerId,currency,
   budget_amount:budgetAmount===null?null:budgetAmount.toFixed(2),
   spent_amount:spent.toFixed(2),
   remaining_amount:remaining===null?null:remaining.toFixed(2),
   over_budget:remaining!==null&&remaining<0,
   unconverted_expense_count:rows.filter(item=>item.currency!==currency).length,
   budgets:store.budgets.filter(item=>String(item.ledger)===String(ledgerId)),
  };
 };
 const handler=async route=>{
  const request=route.request();const method=request.method();const url=new URL(request.url());const path=url.pathname;
  if(path==='/api/expense-ledgers/'&&method==='GET')return json(route,store.ledgers);
  const summaryMatch=path.match(/^\/api\/expense-ledgers\/([^/]+)\/budget-summary\/$/);
  if(summaryMatch&&method==='GET')return json(route,summary(summaryMatch[1]));
  if(path==='/api/expense-budgets/'&&method==='GET'){
   const ledger=url.searchParams.get('ledger');
   return json(route,store.budgets.filter(item=>!ledger||String(item.ledger)===String(ledger)));
  }
  if(path==='/api/expenses/'&&method==='GET'){
   const ledger=url.searchParams.get('ledger')||'ledger-default';
   return json(route,ledgerRows(ledger));
  }
  if(path==='/api/expenses/balance/'&&method==='GET'){
   const ledger=url.searchParams.get('ledger')||'ledger-default';
   const rows=ledgerRows(ledger).filter(item=>item.funding_source!=='shared'&&item.currency===(url.searchParams.get('currency')||'EUR'));
   const total=rows.reduce((sum,item)=>sum+Number(item.total_amount||0),0);
   return json(route,{family:'family-1',ledger,currency:url.searchParams.get('currency')||'EUR',open_amount:(total/2).toFixed(2),members:[
    {id:'member-1',name:'Alex',paid:total.toFixed(2),share:(total/2).toFixed(2),settled_sent:'0.00',settled_received:'0.00',balance:(total/2).toFixed(2)},
    {id:'member-2',name:'Sam',paid:'0.00',share:(total/2).toFixed(2),settled_sent:'0.00',settled_received:'0.00',balance:(-total/2).toFixed(2)},
   ]});
  }
  if(path==='/api/expenses/settlement-plan/'&&method==='GET')return json(route,{family:'family-1',ledger:url.searchParams.get('ledger')||'ledger-default',currency:url.searchParams.get('currency')||'EUR',transfers:[],disclaimer:''});
  if(path==='/api/expenses/settlements/'&&method==='GET')return json(route,[]);
  return route.fallback();
 };
 await page.route(/\/api\/(?:expense-ledgers|expense-budgets|expenses)(?:\/.*)?(?:\?.*)?$/,handler);
 return store;
}

async function boot(page,configure){
 await installApiMocks(page,{dismissOnboarding:true});
 const store=await installBudgetMocks(page);
 configure?.(store);
 await page.goto('/?page=expenses');
 await page.waitForLoadState('networkidle');
 await expect(page.getByRole('heading',{name:'Geld & Finanzen',exact:true})).toBeVisible();
 return store;
}

test('expenses budget · shared spend appears in soft overall and sub-budget progress',async({page})=>{
 await boot(page,store=>{
  store.ledgers[0].budget_amount='40.00';
  store.expenses.push(expense({id:'shared-1',amount:'42.50',funding:'shared',title:'Familieneinkauf'}));
  Object.assign(store.budgets[0],{amount:'30.00',spent_amount:'42.50',remaining_amount:'-12.50',over_budget:true});
 });
 const card=page.locator('.budget-progress-card');
 await expect(card).toBeVisible();
 await expect(card).toContainText('42,50');
 await expect(card).toContainText('40,00');
 await expect(card).toContainText('2,50');
 await expect(card).toContainText('über Budget');
 await card.locator('summary').click();
 await expect(card.getByText('Haushalt',{exact:true})).toBeVisible();
 await expect(card).toContainText('12,50');
 await expect(card).toContainText('Budgetüberschreitungen blockieren keine Ausgabe.');
 await page.locator('.expenses-toolbar').getByRole('button',{name:'Ausgabe',exact:true}).click();
 await expect(page.getByRole('dialog').getByRole('heading',{name:'Neue Ausgabe'})).toBeVisible();
});

test('expenses budget · ledger switch refreshes progress and reports unconverted FX neutrally',async({page})=>{
 await boot(page,store=>{
  store.expenses.push(expense({id:'trip-eur',ledger:'ledger-trip',amount:'120.00',title:'Hotel'}));
  store.expenses.push(expense({id:'trip-usd',ledger:'ledger-trip',amount:'50.00',currency:'USD',title:'Taxi'}));
  Object.assign(store.budgets[1],{spent_amount:'120.00',remaining_amount:'680.00',over_budget:false});
 });
 await page.locator('.expenses-toolbar').getByRole('combobox',{name:'Konto',exact:true}).selectOption('ledger-trip');
 const card=page.locator('.budget-progress-card');
 await expect(card).toContainText('Urlaub');
 await expect(card).toContainText('120,00');
 await expect(card).toContainText('800,00');
 await card.locator('summary').click();
 await expect(card.getByText('Reisebudget',{exact:true})).toBeVisible();
 await expect(card).toContainText('680,00');
 await expect(card).toContainText('1 Fremdwährungs-Ausgabe ist noch nicht im Budget enthalten.');

 await page.setViewportSize({width:390,height:844});
 const dimensions=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth}));
 expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.innerWidth+1);

 await page.locator('.expenses-toolbar').getByRole('combobox',{name:'Konto',exact:true}).selectOption('ledger-default');
 await expect(card).toContainText('Familie – laufend');
 await expect(card).not.toContainText('Fremdwährungs-Ausgabe');
});
