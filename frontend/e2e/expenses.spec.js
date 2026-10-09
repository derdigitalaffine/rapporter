import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}
function empty(route,status=204){return route.fulfill({status,body:''})}

function expenseFrom(body,id='expense-1',source='manual'){
  const participants=(body.participants||['member-1','member-2']).map(String);
  const total=Number(body.total_amount||0);
  const cents=Math.round(total*100);
  const base=Math.floor(cents/participants.length);
  const shares=participants.map((member,index)=>({id:`share-${id}-${index}`,member,member_name:member==='member-1'?'Alex':'Sam',amount:((base+(index<cents-base*participants.length?1:0))/100).toFixed(2),split_type:body.split_type||'equal'}));
  return {
    id,family:body.family||'family-1',title:body.title||body.merchant||'Ausgabe',merchant:body.merchant||body.title||'',occurred_at:body.occurred_at||'2026-10-09T12:00:00.000Z',total_amount:Number(body.total_amount||0).toFixed(2),currency:body.currency||'EUR',paid_by:body.paid_by||'member-1',paid_by_name:(body.paid_by||'member-1')==='member-2'?'Sam':'Alex',created_by:1,receipt_status:source==='receipt'?'ready':'none',receipt_available:source==='receipt',source,status:'posted',notes:'',shares,extraction:source==='receipt'?{id:`extraction-${id}`,status:'ready',merchant:body.merchant||body.title||'',date:(body.occurred_at||'2026-10-09').slice(0,10),total:Number(body.total_amount||0).toFixed(2),subtotal:null,tax:null,currency:body.currency||'EUR',structured_data:{quality_warnings:[]},field_confidences:{merchant:.91,date:.9,total:.94,currency:.96},parser_version:'receipt-v1',processed_at:'2026-10-09T12:00:00.000Z'}:null,
  };
}

async function installExpenseMocks(page){
  const store={expenses:[],settlements:[],receiptDraft:null};
  const handler=async route=>{
    const request=route.request();const method=request.method();const url=new URL(request.url());const path=url.pathname;
    let body={};try{body=request.postDataJSON()||{}}catch{}

    if(path==='/api/expenses/receipt/'&&method==='POST'){
      store.receiptDraft={id:'receipt-1',family:'family-1',title:'',merchant:'',occurred_at:'2026-10-09T12:00:00.000Z',total_amount:null,currency:'EUR',paid_by:'member-1',paid_by_name:'Alex',created_by:1,receipt_status:'queued',receipt_available:true,source:'receipt',status:'draft',notes:'',shares:[],extraction:{id:'extraction-receipt-1',status:'queued',merchant:'',date:null,total:null,subtotal:null,tax:null,currency:'',structured_data:{quality_warnings:[]},field_confidences:{},parser_version:'receipt-v1',processed_at:null},quality_warnings:[]};
      return json(route,store.receiptDraft,202);
    }
    if(path==='/api/expenses/balance/'&&method==='GET'){
      const total=store.expenses.reduce((sum,item)=>sum+Number(item.total_amount||0),0);const open=store.settlements.some(item=>!item.voided_at)?0:total/2;
      return json(route,{family:'family-1',currency:'EUR',open_amount:open.toFixed(2),members:[{id:'member-1',name:'Alex',paid:total.toFixed(2),share:(total/2).toFixed(2),settled_sent:'0.00',settled_received:store.settlements.length?open.toFixed(2):'0.00',balance:open.toFixed(2)},{id:'member-2',name:'Sam',paid:'0.00',share:(total/2).toFixed(2),settled_sent:store.settlements.length?open.toFixed(2):'0.00',settled_received:'0.00',balance:(-open).toFixed(2)}]});
    }
    if(path==='/api/expenses/settlement-plan/'&&method==='GET'){
      const total=store.expenses.reduce((sum,item)=>sum+Number(item.total_amount||0),0);const open=store.settlements.some(item=>!item.voided_at)?0:total/2;
      return json(route,{family:'family-1',currency:'EUR',transfers:open?[{from_member:'member-2',from_name:'Sam',to_member:'member-1',to_name:'Alex',amount:open.toFixed(2)}]:[],disclaimer:'Dokumentiert eine Abrechnung in Rapporter; führt keine reale Zahlung aus.'});
    }
    if(path==='/api/expenses/settlements/'&&method==='GET')return json(route,store.settlements);
    if(path==='/api/expenses/settlements/'&&method==='POST'){
      const settlement={id:`settlement-${store.settlements.length+1}`,...body,from_name:body.from_member==='member-2'?'Sam':'Alex',to_name:body.to_member==='member-1'?'Alex':'Sam',settled_at:'2026-10-09T12:00:00.000Z',voided_at:null,created_at:'2026-10-09T12:00:00.000Z'};store.settlements.unshift(settlement);return json(route,settlement,201);
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
        const source=id==='receipt-1'?'receipt':'manual';const saved=expenseFrom(body,id,source);const index=store.expenses.findIndex(item=>item.id===id);if(index>=0)store.expenses[index]=saved;else store.expenses.unshift(saved);if(source==='receipt')store.receiptDraft=saved;return json(route,saved);
      }
      if(method==='DELETE'){store.expenses=store.expenses.filter(item=>item.id!==id);return empty(route)}
      const found=store.expenses.find(item=>item.id===id);return found?json(route,found):json(route,{detail:'Not found'},404);
    }
    if(path==='/api/expenses/'&&method==='GET')return json(route,store.expenses);
    if(path==='/api/expenses/'&&method==='POST'){
      const saved=expenseFrom(body,`expense-${store.expenses.length+1}`);store.expenses.unshift(saved);return json(route,saved,201);
    }
    return route.fallback();
  };
  await page.route(/\/api\/expenses(?:\/.*)?(?:\?.*)?$/,handler);
  return store;
}

async function boot(page,path='/'){
  await installApiMocks(page,{dismissOnboarding:true});
  const store=await installExpenseMocks(page);
  await page.goto(path);await page.waitForLoadState('networkidle');await expect(page.locator('.app-shell')).toBeVisible();
  return store;
}

test('expenses · reachable from More, manual split and one-click settlement',async({page})=>{
  await boot(page);
  await page.locator('.bottom-nav').getByRole('button',{name:'Mehr'}).click();
  await page.getByRole('button',{name:'Ausgabe',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Ausgaben',exact:true})).toBeVisible();
  await expect(page.locator('.bottom-nav')).toHaveCount(0);

  await page.locator('.global-create-fab').click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByRole('heading',{name:'Ausgabe hinzufügen'})).toBeVisible();
  await dialog.getByRole('button',{name:'Ohne Beleg eingeben'}).click();
  await dialog.getByLabel('Händler / Titel').fill('Supermarkt');
  await dialog.getByLabel('Betrag').fill('12.34');
  await dialog.getByLabel('Bezahlt von').selectOption('member-1');
  await expect(dialog.getByRole('button',{name:/Alex/})).toHaveAttribute('aria-pressed','true');
  await expect(dialog.getByRole('button',{name:/Sam/})).toHaveAttribute('aria-pressed','true');
  await dialog.getByRole('button',{name:'Ausgabe speichern'}).click();

  await expect(page.getByText('Supermarkt',{exact:true})).toBeVisible();
  await expect(page.getByText('Sam → Alex',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Als abgerechnet markieren'}).click();
  await expect(page.locator('.balance-total')).toContainText('Alles ausgeglichen');
  await expect(page.getByText('Rapporter dokumentiert die Abrechnung nur. Es wird kein Geld übertragen.')).toBeVisible();
});

test('expenses · receipt upload becomes OCR review with editable confidences',async({page})=>{
  await boot(page,'/?page=expenses');
  await page.locator('.global-create-fab').click();
  const dialog=page.getByRole('dialog');
  await dialog.locator('input[capture="environment"]').setInputFiles({name:'receipt.png',mimeType:'image/png',buffer:Buffer.from('mock-receipt')});
  await expect(dialog.getByText('Kurz prüfen',{exact:true})).toBeVisible({timeout:8000});
  await expect(dialog.getByLabel('Händler / Titel')).toHaveValue('REWE MARKT');
  await expect(dialog.getByLabel('Betrag')).toHaveValue('12.34');
  await expect(dialog.getByText(/94% · sicher/)).toBeVisible();
  await dialog.getByLabel('Bezahlt von').selectOption('member-1');
  await dialog.getByRole('button',{name:'Ausgabe speichern'}).click();
  await expect(page.getByText('REWE MARKT',{exact:true})).toBeVisible();
});

test('expenses · no horizontal overflow on phone, tablet landscape and desktop',async({page})=>{
  await boot(page,'/?page=expenses');
  for(const viewport of [{width:390,height:844},{width:1024,height:768},{width:1440,height:900}]){
    await page.setViewportSize(viewport);
    await expect(page.getByRole('heading',{name:'Ausgaben',exact:true})).toBeVisible();
    const dimensions=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth}));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.innerWidth+1);
  }
});
