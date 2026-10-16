import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
import {openCreateAction} from './create-helpers';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}
function empty(route,status=204){return route.fulfill({status,body:''})}

function queuedDraft(){
 return {
  id:'receipt-intelligence-1',family:'family-1',ledger:'ledger-default',title:'',merchant:'',category:'',
  occurred_at:'2026-10-17T12:00:00.000Z',total_amount:null,currency:'EUR',funding_source:'member',
  paid_by:'member-1',paid_by_name:'Alex',created_by:1,receipt_status:'queued',receipt_available:true,
  receipt_mime:'image/webp',source:'receipt',status:'draft',notes:'',shares:[],
  extraction:{id:'extraction-receipt-intelligence-1',status:'queued',merchant:'',date:null,total:null,subtotal:null,tax:null,currency:'',field_confidences:{},quality_warnings:[],structured_data:{},parser_version:'receipt-v1',processed_at:null},
 };
}

function reviewedDraft(base){
 return {
  ...base,title:'REWE MARKT',merchant:'REWE MARKT',occurred_at:'2026-10-16T12:00:00.000Z',total_amount:'12.34',currency:'EUR',receipt_status:'review',
  extraction:{
   ...base.extraction,status:'review',merchant:'REWE MARKT',date:'2026-10-16',total:'12.34',subtotal:'11.53',tax:'0.81',currency:'EUR',parser_version:'receipt-v2',processed_at:'2026-10-17T12:00:00.000Z',
   field_confidences:{merchant:.91,date:.90,time:.88,total:.74,currency:.98,subtotal:.91,tax:.91,receipt_id:.92},
   structured_data:{
    schema_version:2,extractor_version:'receipt-v2',ocr_confidence:.61,semantic_confidence:.856,
    fields:{
     merchant:{raw:'REWE MARKT',normalized:'REWE MARKT',semantic_confidence:.91},
     date:{raw:'16.10.2026',normalized:'2026-10-16',semantic_confidence:.90},
     time:{raw:'18:42',normalized:'18:42',semantic_confidence:.88},
     currency:{raw:'EUR',normalized:'EUR',semantic_confidence:.98},
     total:{raw:'SUMME EUR 12,34',normalized:'12.34',semantic_confidence:.74,ambiguous:true},
     subtotal:{raw:'ZWISCHENSUMME 11,53',normalized:'11.53',semantic_confidence:.91},
     tax:{raw:'MWST 0,81',normalized:'0.81',semantic_confidence:.91},
     receipt_id:{raw:'Beleg-Nr 4711-A',normalized:'4711-A',semantic_confidence:.92},
    },
    total_candidates:[
     {amount:'12.34',score:.84,line:'SUMME EUR 12,34'},
     {amount:'12.50',score:.79,line:'GESAMT EUR 12,50'},
    ],
    line_items:[
     {description:'MILCH 1L',total:'1.29',raw:'MILCH 1L 1,29',line_index:4,semantic_confidence:.82},
     {description:'BROT',total:'2.49',raw:'BROT 2,49',line_index:5,semantic_confidence:.81},
    ],
    reconciliation:{
     status:'mismatch',item_sum:'3.78',checks:[{kind:'line_items_vs_subtotal',actual:'3.78',expected:'11.53',delta:'-7.75',tolerance:'0.02',matched:false,authoritative:true}],
    },
    review:{needs_review:true,reasons:['total_ambiguous','reconciliation_mismatch']},
   },
   quality_warnings:[],
  },
 };
}

async function installReceiptIntelligenceMocks(page){
 const state={draft:null,savedPayload:null};
 const ledger={id:'ledger-default',family:'family-1',name:'Familie – laufend',base_currency:'EUR',budget_amount:'500.00',is_default:true,archived:false};
 const handler=async route=>{
  const request=route.request();const method=request.method();const url=new URL(request.url());const path=url.pathname;
  let body={};try{body=request.postDataJSON()||{}}catch{}

  if(path==='/api/expense-ledgers/'&&method==='GET')return json(route,[ledger]);
  if(path==='/api/expense-budgets/'&&method==='GET')return json(route,[]);
  if(path==='/api/expenses/'&&method==='GET')return json(route,[]);
  if(path==='/api/expenses/balance/'&&method==='GET')return json(route,{family:'family-1',ledger:'ledger-default',currency:'EUR',open_amount:'0.00',members:[{id:'member-1',name:'Alex',paid:'0.00',share:'0.00',settled_sent:'0.00',settled_received:'0.00',balance:'0.00'},{id:'member-2',name:'Sam',paid:'0.00',share:'0.00',settled_sent:'0.00',settled_received:'0.00',balance:'0.00'}]});
  if(path==='/api/expenses/settlement-plan/'&&method==='GET')return json(route,{family:'family-1',ledger:'ledger-default',currency:'EUR',transfers:[],disclaimer:''});
  if(path==='/api/expenses/settlements/'&&method==='GET')return json(route,[]);

  if(path==='/api/expenses/receipt/'&&method==='POST'){
   state.draft=queuedDraft();
   return json(route,state.draft,202);
  }
  if(path==='/api/expenses/receipt-intelligence-1/budget-allocations/'&&method==='GET')return json(route,{expense:'receipt-intelligence-1',ledger:'ledger-default',currency:'EUR',allocations:[]});
  if(path==='/api/expenses/receipt-intelligence-1/receipt-file/'&&method==='GET')return empty(route);
  if(path==='/api/expenses/receipt-intelligence-1/'&&method==='GET'){
   state.draft=reviewedDraft(state.draft||queuedDraft());
   return json(route,state.draft);
  }
  if(path==='/api/expenses/receipt-intelligence-1/'&&method==='PATCH'){
   state.savedPayload=body;
   const saved={...reviewedDraft(state.draft||queuedDraft()),...body,status:'posted',receipt_status:'ready',shares:[{id:'share-1',member:'member-1',member_name:'Alex',amount:'6.17',split_type:'equal'},{id:'share-2',member:'member-2',member_name:'Sam',amount:'6.17',split_type:'equal'}]};
   state.draft=saved;
   return json(route,saved);
  }
  return route.fallback();
 };
 await page.route(/\/api\/(?:expense-ledgers|expense-budgets|expenses)(?:\/.*)?(?:\?.*)?$/,handler);
 return state;
}

async function boot(page){
 await installApiMocks(page,{dismissOnboarding:true});
 const state=await installReceiptIntelligenceMocks(page);
 await page.goto('/?page=expenses&finance=expenses');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.app-shell')).toBeVisible();
 return state;
}

test('expenses · receipt intelligence v2 is visible, explainable and review-only',async({page})=>{
 const state=await boot(page);
 await openCreateAction(page,'Geld & Finanzen');
 const dialog=page.getByRole('dialog');
 await dialog.getByRole('button',{name:'Beleg scannen'}).click();
 await dialog.locator('input[capture="environment"]').setInputFiles({name:'receipt.png',mimeType:'image/png',buffer:Buffer.from('mock-receipt')});

 await expect(dialog.getByRole('heading',{name:'Beleg-Erkennung'})).toBeVisible({timeout:8000});
 await expect(dialog.getByText('OCR-Lesbarkeit')).toBeVisible();
 await expect(dialog.getByText('61%',{exact:true})).toBeVisible();
 await expect(dialog.getByText('Feld-Erkennung')).toBeVisible();
 await expect(dialog.getByText('86%',{exact:true})).toBeVisible();
 await expect(dialog.getByText('Mehrere Gesamtbeträge sind ähnlich plausibel.')).toBeVisible();
 await expect(dialog.getByText('Erkannte Summen und Positionen passen nicht zusammen.')).toBeVisible();
 await expect(dialog.getByText('Zwischensumme')).toBeVisible();
 await expect(dialog.getByText('11,53 €')).toBeVisible();
 await expect(dialog.getByText('MwSt. / Steuer')).toBeVisible();
 await expect(dialog.getByText('0,81 €')).toBeVisible();
 await expect(dialog.getByText('Beleg-/Transaktionsnummer')).toBeVisible();
 await expect(dialog.getByText('4711-A')).toBeVisible();
 await expect(dialog.getByText('Summen weichen voneinander ab – bitte Beleg und Betrag prüfen.')).toBeVisible();

 await dialog.getByText('Erkannte Positionen',{exact:true}).click();
 await expect(dialog.getByText('MILCH 1L',{exact:true})).toBeVisible();
 await expect(dialog.getByText(/Positionen werden nicht automatisch aufgeteilt oder gebucht/)).toBeVisible();
 await dialog.getByText('Evidence anzeigen',{exact:true}).click();
 await expect(dialog.getByText('SUMME EUR 12,34',{exact:true})).toBeVisible();
 await expect(dialog.getByText('12.34',{exact:true})).toBeVisible();

 await expect(dialog.getByLabel('Händler / Titel')).toHaveValue('REWE MARKT');
 await expect(dialog.getByLabel('Betrag')).toHaveValue('12.34');
 await dialog.getByRole('button',{name:'Ausgabe speichern'}).click();
 await expect.poll(()=>state.savedPayload).not.toBeNull();
 expect(state.savedPayload.finalize).toBe(true);
 expect(state.savedPayload.total_amount).toBe('12.34');
 expect(state.savedPayload).not.toHaveProperty('structured_data');
 expect(state.savedPayload).not.toHaveProperty('line_items');
 expect(state.savedPayload).not.toHaveProperty('reconciliation');
});
