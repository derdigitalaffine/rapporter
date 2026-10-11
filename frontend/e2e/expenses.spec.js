import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}
function empty(route,status=204){return route.fulfill({status,body:''})}

function expenseFrom(body,id='expense-1',source='manual'){
  const funding=body.funding_source||'member';
  const participants=funding==='shared'?[]:(body.participants||['member-1','member-2']).map(String);
  const total=Number(body.total_amount||0);
  const cents=Math.round(total*100);
  const base=participants.length?Math.floor(cents/participants.length):0;
  const shares=participants.map((member,index)=>({id:`share-${id}-${index}`,member,member_name:member==='member-1'?'Alex':'Sam',amount:((base+(index<cents-base*participants.length?1:0))/100).toFixed(2),split_type:body.split_type||'equal'}));
  const paidBy=funding==='shared'?null:(body.paid_by||'member-1');
  return {
    id,family:body.family||'family-1',ledger:body.ledger||'ledger-default',title:body.title||body.merchant||'Ausgabe',merchant:body.merchant||body.title||'',occurred_at:body.occurred_at||'2026-10-09T12:00:00.000Z',total_amount:Number(body.total_amount||0).toFixed(2),currency:body.currency||'EUR',funding_source:funding,paid_by:paidBy,paid_by_name:paidBy?(paidBy==='member-2'?'Sam':'Alex'):null,created_by:1,receipt_status:source==='receipt'?'ready':'none',receipt_available:source==='receipt',source,status:'posted',notes:'',shares,extraction:source==='receipt'?{id:`extraction-${id}`,status:'ready',merchant:body.merchant||body.title||'',date:(body.occurred_at||'2026-10-09').slice(0,10),total:Number(body.total_amount||0).toFixed(2),subtotal:null,tax:null,currency:body.currency||'EUR',structured_data:{quality_warnings:[]},field_confidences:{merchant:.91,date:.9,total:.94,currency:.96},parser_version:'receipt-v1',processed_at:'2026-10-09T12:00:00.000Z'}:null,
  };
}

async function installExpenseMocks(page){
  const store={
    expenses:[],settlements:[],receiptDraft:null,requestIds:new Map(),allocations:new Map(),
    ledgers:[
      {id:'ledger-default',family:'family-1',name:'Familie – laufend',base_currency:'EUR',budget_amount:'500.00',is_default:true,archived:false},
      {id:'ledger-trip',family:'family-1',name:'Urlaub',base_currency:'EUR',budget_amount:'800.00',is_default:false,archived:false},
    ],
    budgets:[
      {id:'budget-home',family:'family-1',ledger:'ledger-default',name:'Haushalt',amount:'300.00',currency:'EUR',archived:false,spent_amount:'0.00',remaining_amount:'300.00',over_budget:false},
      {id:'budget-trip',family:'family-1',ledger:'ledger-trip',name:'Reisebudget',amount:'800.00',currency:'EUR',archived:false,spent_amount:'0.00',remaining_amount:'800.00',over_budget:false},
    ],
  };
  const scopedExpenses=url=>{
    const ledger=url.searchParams.get('ledger')||'ledger-default';
    return store.expenses.filter(item=>String(item.ledger||'ledger-default')===String(ledger));
  };
  const balanceRows=url=>{
    const rows=scopedExpenses(url).filter(item=>item.funding_source!=='shared');
    const total=rows.reduce((sum,item)=>sum+Number(item.total_amount||0),0);
    const ledger=url.searchParams.get('ledger')||'ledger-default';
    const activeSettlements=store.settlements.filter(item=>!item.voided_at&&String(item.ledger||'ledger-default')===String(ledger));
    const open=activeSettlements.length?0:total/2;
    return {total,open,ledger};
  };
  const handler=async route=>{
    const request=route.request();const method=request.method();const url=new URL(request.url());const path=url.pathname;
    let body={};try{body=request.postDataJSON()||{}}catch{}

    if(path==='/api/expense-ledgers/'&&method==='GET')return json(route,store.ledgers);
    if(path==='/api/expense-budgets/'&&method==='GET'){
      const ledger=url.searchParams.get('ledger');
      return json(route,store.budgets.filter(item=>!ledger||String(item.ledger)===String(ledger)));
    }
    if(/^\/api\/expenses\/[^/]+\/budget-allocations\/$/.test(path)){
      const id=path.split('/')[3];
      const expense=store.expenses.find(item=>item.id===id)||store.receiptDraft;
      const ledger=expense?.ledger||'ledger-default';
      if(method==='GET')return json(route,{expense:id,ledger,currency:'EUR',allocations:store.allocations.get(id)||[]});
      if(method==='PUT'){
        const allocations=(body.allocations||[]).map(row=>({budget:String(row.budget),budget_name:store.budgets.find(item=>String(item.id)===String(row.budget))?.name||'',amount_in_budget_currency:Number(row.amount_in_budget_currency).toFixed(2)}));
        store.allocations.set(id,allocations);
        return json(route,{expense:id,ledger,currency:'EUR',allocations});
      }
    }
    if(path==='/api/expenses/receipt/'&&method==='POST'){
      store.receiptDraft={id:'receipt-1',family:'family-1',ledger:'ledger-default',title:'',merchant:'',occurred_at:'2026-10-09T12:00:00.000Z',total_amount:null,currency:'EUR',funding_source:'member',paid_by:'member-1',paid_by_name:'Alex',created_by:1,receipt_status:'queued',receipt_available:true,source:'receipt',status:'draft',notes:'',shares:[],extraction:{id:'extraction-receipt-1',status:'queued',merchant:'',date:null,total:null,subtotal:null,tax:null,currency:'',structured_data:{quality_warnings:[]},field_confidences:{},parser_version:'receipt-v1',processed_at:null},quality_warnings:[]};
      return json(route,store.receiptDraft,202);
    }
    if(path==='/api/expenses/balance/'&&method==='GET'){
      const {total,open,ledger}=balanceRows(url);
      return json(route,{family:'family-1',ledger,currency:url.searchParams.get('currency')||'EUR',open_amount:open.toFixed(2),members:[{id:'member-1',name:'Alex',paid:total.toFixed(2),share:(total/2).toFixed(2),settled_sent:'0.00',settled_received:store.settlements.length?open.toFixed(2):'0.00',balance:open.toFixed(2)},{id:'member-2',name:'Sam',paid:'0.00',share:(total/2).toFixed(2),settled_sent:store.settlements.length?open.toFixed(2):'0.00',settled_received:'0.00',balance:(-open).toFixed(2)}]});
    }
    if(path==='/api/expenses/settlement-plan/'&&method==='GET'){
      const {open,ledger}=balanceRows(url);
      return json(route,{family:'family-1',ledger,currency:url.searchParams.get('currency')||'EUR',transfers:open?[{from_member:'member-2',from_name:'Sam',to_member:'member-1',to_name:'Alex',amount:open.toFixed(2)}]:[],disclaimer:'Dokumentiert eine Abrechnung in Rapporter; führt keine reale Zahlung aus.'});
    }
    if(path==='/api/expenses/settlements/'&&method==='GET'){
      const ledger=url.searchParams.get('ledger')||'ledger-default';
      return json(route,store.settlements.filter(item=>String(item.ledger||'ledger-default')===String(ledger)));
    }
    if(path==='/api/expenses/settlements/'&&method==='POST'){
      const settlement={id:`settlement-${store.settlements.length+1}`,...body,ledger:body.ledger||'ledger-default',from_name:body.from_member==='member-2'?'Sam':'Alex',to_name:body.to_member==='member-1'?'Alex':'Sam',settled_at:'2026-10-09T12:00:00.000Z',voided_at:null,created_at:'2026-10-09T12:00:00.000Z'};store.settlements.unshift(settlement);return json(route,settlement,201);
    }
    if(/^\/api\/expenses\/settlements\/[^/]+\/void\/$/.test(path)&&method==='POST'){
      const id=path.split('/')[4];const settlement=store.settlements.find(item=>item.id===id);if(settlement)settlement.voided_at='2026-10-09T12:01:00.000Z';return json(route,settlement||{});
    }
    if(/^\/api\/expenses\/[^/]+\/receipt-file\/$/.test(path)){
      if(method==='DELETE'){if(store.receiptDraft)store.receiptDraft.receipt_available=false;return empty(route)}
      return empty(route);
    }
    if(/^\/api\/expenses\/[^/]+\/retry-receipt\/$/.test(path)&&method==='POST')return json(route,{status:'queued'},202);
    if(/^\/api\/expenses\/[^/]+\/$/.test(path)){
      const id=path.split('/')[3];
      if(method==='GET'&&id==='receipt-1')return json(route,{...store.receiptDraft,title:'REWE MARKT',merchant:'REWE MARKT',total_amount:'12.34',receipt_status:'review',extraction:{...store.receiptDraft.extraction,status:'review',merchant:'REWE MARKT',date:'2026-10-08',total:'12.34',currency:'EUR',field_confidences:{merchant:.91,date:.9,total:.94,currency:.96},processed_at:'2026-10-09T12:00:00.000Z'}});
      if(method==='PATCH'){
        const source=id==='receipt-1'?'receipt':'manual';
        const previous=store.expenses.find(item=>item.id===id)||store.receiptDraft||{};
        const saved=expenseFrom({...previous,...body},id,source);
        if(previous.total_amount!==undefined&&(String(previous.total_amount)!==String(saved.total_amount)||String(previous.ledger)!==String(saved.ledger)))store.allocations.delete(id);
        const index=store.expenses.findIndex(item=>item.id===id);if(index>=0)store.expenses[index]=saved;else store.expenses.unshift(saved);if(source==='receipt')store.receiptDraft=saved;return json(route,saved);
      }
      if(method==='DELETE'){store.expenses=store.expenses.filter(item=>item.id!==id);store.allocations.delete(id);return empty(route)}
      const found=store.expenses.find(item=>item.id===id);return found?json(route,found):json(route,{detail:'Not found'},404);
    }
    if(path==='/api/expenses/'&&method==='GET')return json(route,scopedExpenses(url));
    if(path==='/api/expenses/'&&method==='POST'){
      if(body.client_request_id&&store.requestIds.has(body.client_request_id))return json(route,store.requestIds.get(body.client_request_id),201);
      const saved=expenseFrom(body,`expense-${store.expenses.length+1}`);store.expenses.unshift(saved);if(body.client_request_id)store.requestIds.set(body.client_request_id,saved);return json(route,saved,201);
    }
    return route.fallback();
  };
  await page.route(/\/api\/(?:expense-ledgers|expense-budgets|expenses)(?:\/.*)?(?:\?.*)?$/,handler);
  return store;
}

async function boot(page,path='/',options={}){
  await installApiMocks(page,{dismissOnboarding:true,...options});
  const store=await installExpenseMocks(page);
  await page.goto(path);await page.waitForLoadState('networkidle');await expect(page.locator('.app-shell')).toBeVisible();
  return store;
}

test('expenses · two-tap quick add uses visible safe defaults and updates balance',async({page})=>{
  const store=await boot(page);
  await page.locator('.bottom-nav').getByRole('button',{name:'Mehr'}).click();
  await page.getByRole('button',{name:'Ausgabe',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Ausgaben',exact:true})).toBeVisible();
  await expect(page.locator('.bottom-nav')).toHaveCount(0);

  await page.locator('.expenses-toolbar').getByRole('button',{name:'Ausgabe',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByRole('heading',{name:'Neue Ausgabe'})).toBeVisible();
  const amount=dialog.getByLabel('Betrag');
  await expect(amount).toBeFocused();
  await expect(dialog.getByText(/Du hast bezahlt · gleichmäßig für/)).toBeVisible();
  await expect(dialog.getByText(/Alex/)).toBeVisible();
  await expect(dialog.getByText(/Sam/)).toBeVisible();
  await amount.fill('12,50');
  await dialog.getByRole('button',{name:'Speichern',exact:true}).click();

  await expect(page.locator('.expense-row-main strong').first()).toHaveText('Ausgabe');
  expect(store.expenses).toHaveLength(1);
  expect(store.expenses[0].source).toBe('manual');
  expect(store.expenses[0].funding_source).toBe('member');
  expect(store.expenses[0].ledger).toBe('ledger-default');
  expect(store.expenses[0].paid_by).toBe('member-1');
  expect(store.expenses[0].shares).toHaveLength(2);
  await expect(page.getByText('Sam → Alex',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Als abgerechnet markieren'}).click();
  await expect(page.locator('.balance-total')).toContainText('Alles ausgeglichen');
  expect(store.settlements[0].ledger).toBe('ledger-default');
  await expect(page.getByText('Rapporter dokumentiert die Abrechnung nur. Es wird kein Geld übertragen.')).toBeVisible();
});

test('expenses · details expose shared funding, ledger and one standard budget without person debt',async({page})=>{
  const store=await boot(page,'/?page=expenses');
  await page.locator('.expenses-toolbar').getByRole('button',{name:'Ausgabe',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Betrag').fill('42,50');
  await dialog.getByLabel(/Du hast bezahlt/).click();
  await expect(dialog.getByText('Zahlungsart',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Gemeinsam bezahlt',exact:true}).click();
  await expect(dialog.getByText(/verändert keinen Personensaldo/)).toBeVisible();
  await expect(dialog.getByLabel('Bezahlt von')).toHaveCount(0);
  await expect(dialog.getByText('Für wen?',{exact:true})).toHaveCount(0);
  await expect(dialog.getByLabel('Abrechnungskreis')).toBeVisible();
  await expect(dialog.getByLabel('Budgettopf (optional)')).toBeVisible();
  await dialog.getByLabel('Budgettopf (optional)').selectOption('budget-home');
  await dialog.getByRole('button',{name:'Ausgabe speichern'}).click();

  expect(store.expenses).toHaveLength(1);
  expect(store.expenses[0].funding_source).toBe('shared');
  expect(store.expenses[0].paid_by).toBeNull();
  expect(store.expenses[0].shares).toHaveLength(0);
  expect(store.allocations.get(store.expenses[0].id)).toEqual([{budget:'budget-home',budget_name:'Haushalt',amount_in_budget_currency:'42.50'}]);
  await expect(page.locator('.expense-row-main small').first()).toContainText('gemeinsam bezahlt');
  await expect(page.locator('.expense-row-amount small').first()).toHaveText('ohne Personensplit');
  await expect(page.locator('.balance-total')).toContainText('Alles ausgeglichen');
  await expect(page.getByRole('button',{name:'Als abgerechnet markieren'})).toHaveCount(0);
});

test('expenses · ledger selector scopes list and balances to one ledger',async({page})=>{
  const store=await boot(page,'/?page=expenses');
  store.expenses.push(expenseFrom({family:'family-1',ledger:'ledger-trip',title:'Hotel',total_amount:'120.00',currency:'EUR',paid_by:'member-1',participants:['member-1','member-2']},'trip-expense'));
  await page.getByLabel('Abrechnungskreis').selectOption('ledger-trip');
  await expect(page.getByText('Hotel',{exact:true})).toBeVisible();
  await expect(page.locator('.balance-card-head').getByText('Urlaub',{exact:true})).toBeVisible();
  await expect(page.getByText('Sam → Alex',{exact:true})).toBeVisible();
  await page.getByLabel('Abrechnungskreis').selectOption('ledger-default');
  await expect(page.getByText('Hotel',{exact:true})).toHaveCount(0);
});

test('expenses · quick add opens advanced #114 split options without losing input',async({page})=>{
  await boot(page,'/?page=expenses');
  await page.locator('.expenses-toolbar').getByRole('button',{name:'Ausgabe',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Betrag').fill('10.00');
  await dialog.getByLabel(/Du hast bezahlt/).click();
  await expect(dialog.getByLabel('Bezahlt von')).toBeVisible();
  await expect(dialog.getByLabel('Betrag')).toHaveValue('10.00');
  await expect(dialog.getByRole('button',{name:'Gleichmäßig'})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Exakte Beträge'})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Prozent'})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Anteile'})).toBeVisible();
});

test('expenses · quick add undo deletes exactly the created expense',async({page})=>{
  const store=await boot(page,'/?page=expenses');
  await page.locator('.expenses-toolbar').getByRole('button',{name:'Ausgabe',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Betrag').fill('8,00');
  await dialog.getByLabel('Wofür? (optional)').fill('Parken');
  await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
  await expect(page.locator('.expense-row-main strong').first()).toHaveText('Parken');
  await page.getByRole('button',{name:'Rückgängig'}).click();
  await expect.poll(()=>store.expenses.length).toBe(0);
  await expect(page.locator('.expense-row-main strong')).toHaveCount(0);
});

test('expenses · receipt upload remains available from quick add and becomes OCR review',async({page})=>{
  await boot(page,'/?page=expenses');
  await page.locator('.global-create-fab').click();
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('button',{name:'Beleg scannen'}).click();
  await dialog.locator('input[capture="environment"]').setInputFiles({name:'receipt.png',mimeType:'image/png',buffer:Buffer.from('mock-receipt')});
  await expect(dialog.getByText('Kurz prüfen',{exact:true})).toBeVisible({timeout:8000});
  await expect(dialog.getByLabel('Händler / Titel')).toHaveValue('REWE MARKT');
  await expect(dialog.getByLabel('Betrag')).toHaveValue('12.34');
  await expect(dialog.getByText(/94% · sicher/)).toBeVisible();
  await dialog.getByLabel('Bezahlt von').selectOption('member-1');
  await dialog.getByRole('button',{name:'Ausgabe speichern'}).click();
  await expect(page.getByText('REWE MARKT',{exact:true})).toBeVisible();
});

test('expenses · shared funding controls are keyboard reachable and available in English',async({page})=>{
  await boot(page,'/?page=expenses',{language:'en'});
  await page.locator('.expenses-toolbar').getByRole('button',{name:'Expense',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Amount').fill('15.00');
  await dialog.getByLabel(/You paid/).press('Enter');
  const shared=dialog.getByRole('button',{name:'Paid jointly',exact:true});
  await shared.focus();
  await expect(shared).toBeFocused();
  await shared.press('Enter');
  await expect(shared).toHaveAttribute('aria-pressed','true');
  await expect(dialog.getByText(/does not change personal balances/)).toBeVisible();
});

test('expenses · no horizontal overflow on phone, tablet landscape and desktop',async({page})=>{
  await boot(page,'/?page=expenses');
  for(const viewport of [{width:390,height:844},{width:1024,height:768},{width:1440,height:900}]){
    await page.setViewportSize(viewport);
    await expect(page.getByRole('heading',{name:'Ausgaben',exact:true})).toBeVisible();
    const dimensions=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth}));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.innerWidth+1);
  }
  await page.setViewportSize({width:390,height:844});
  await page.locator('.expenses-toolbar').getByRole('button',{name:'Ausgabe',exact:true}).click();
  await expect(page.getByRole('dialog').getByLabel('Betrag')).toBeFocused();
  await page.getByRole('dialog').getByLabel(/Du hast bezahlt/).click();
  const dialogDimensions=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth}));
  expect(dialogDimensions.scrollWidth).toBeLessThanOrEqual(dialogDimensions.innerWidth+1);
});