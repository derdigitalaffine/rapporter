import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const normalize=value=>value===null||value===undefined||value===''?null:Number(String(value).replace(',','.')).toFixed(2);

test('finance · participant limits and planned shares stay planning-only in the existing budget editor',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true,language:'de'});
 const ledger={id:'ledger-home',family:'family-1',name:'Familie',base_currency:'EUR',budget_amount:null,estimated_amount:null,is_default:true,archived:false,updated_at:'2026-10-14T10:00:00Z'};
 const budgets=[];
 const participantPlans=new Map();
 const writes=[];

 await page.route(/\/api\/expense-(?:ledgers|budgets)\//,async route=>{
  const request=route.request();
  const path=new URL(request.url()).pathname;
  const method=request.method();
  if(path==='/api/expense-ledgers/'&&method==='GET')return json(route,[ledger]);
  if(path==='/api/expense-ledgers/ledger-home/budget-summary/'&&method==='GET')return json(route,{
   family:'family-1',ledger:ledger.id,currency:'EUR',budget_amount:null,estimated_amount:null,updated_at:ledger.updated_at,spent_amount:'0.00',reserved_amount:'0.00',remaining_amount:null,available_amount:null,over_budget:false,over_available:false,unconverted_expense_count:0,budgets,
  });
  if(path==='/api/expense-budgets/'&&method==='GET')return json(route,budgets);
  const participantMatch=path.match(/^\/api\/expense-budgets\/([^/]+)\/participant-plans\/$/);
  if(participantMatch&&method==='GET')return json(route,{scope_type:'budget',scope_id:participantMatch[1],currency:'EUR',can_manage:true,plans:participantPlans.get(participantMatch[1])||[]});
  if(path==='/api/expense-budgets/'&&method==='POST'){
   const body=request.postDataJSON();writes.push(body);
   const id='budget-1';
   const plans=(body.participant_plans||[]).map(row=>({member:row.member,member_name:row.member==='member-1'?'Alex':'Sam',spending_limit:normalize(row.spending_limit),planned_share:normalize(row.planned_share),spending_limit_visible:true}));
   participantPlans.set(id,plans);
   const row={id,family:'family-1',ledger:'ledger-home',parent:null,name:body.name,amount:normalize(body.amount),estimated_amount:null,currency:'EUR',period_type:body.period_type||'open',rollover_policy:null,period_starts_on:null,period_ends_on:null,starts_on:null,ends_on:null,carryover_amount:'0.00',spent_amount:'0.00',reserved_amount:'0.00',remaining_amount:normalize(body.amount),available_amount:normalize(body.amount),over_budget:false,over_available:false,archived:false,updated_at:'2026-10-14T10:01:00Z'};
   budgets.push(row);return json(route,row,201);
  }
  const budgetMatch=path.match(/^\/api\/expense-budgets\/([^/]+)\/$/);
  if(budgetMatch&&method==='PATCH'){
   const body=request.postDataJSON();writes.push(body);
   const row=budgets.find(item=>item.id===budgetMatch[1]);
   if(body.participant_plans){participantPlans.set(row.id,body.participant_plans.map(plan=>({member:plan.member,member_name:plan.member==='member-1'?'Alex':'Sam',spending_limit:normalize(plan.spending_limit),planned_share:normalize(plan.planned_share),spending_limit_visible:true})))}
   Object.assign(row,{...body,amount:body.amount?normalize(body.amount):row.amount,updated_at:'2026-10-14T10:02:00Z'});delete row.participant_plans;return json(route,row);
  }
  return route.fallback();
 });

 await page.setViewportSize({width:320,height:844});
 await page.goto('/?page=expenses&ledger=ledger-home');
 await page.waitForLoadState('networkidle');
 const planner=page.getByRole('region',{name:'Budget',exact:true});
 const categories=planner.locator('details.finance-collapsible').first();
 await categories.locator('summary').click();
 await planner.getByRole('button',{name:'Kostenbereich hinzufügen',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Kostenbereich hinzufügen'});
 await dialog.getByRole('textbox',{name:'Kostenbereich',exact:true}).fill('Freizeit');
 await dialog.getByRole('textbox',{name:'Geplant (EUR)',exact:true}).fill('100');

 const participantSection=dialog.locator('details.budget-participant-settings');
 await expect(participantSection.getByText('Teilnehmerplanung',{exact:true})).toBeVisible();
 await expect(participantSection).not.toHaveAttribute('open','');
 await participantSection.locator('summary').click();
 await expect(dialog.getByText(/keine Ausgabe, Schuld oder Abrechnung/)).toBeVisible();
 await dialog.getByLabel('Persönliches Limit · Alex (EUR)',{exact:true}).fill('80,50');
 await dialog.getByLabel('Geplanter Kostenanteil · Alex (EUR)',{exact:true}).fill('60');
 await dialog.getByLabel('Geplanter Kostenanteil · Sam (EUR)',{exact:true}).fill('40');
 await expect(dialog.getByText('Geplante Kostenanteile zusammen',{exact:true})).toBeVisible();
 await expect(dialog).toContainText('100,00');
 await dialog.getByRole('button',{name:'Budget speichern',exact:true}).click();

 expect(writes).toHaveLength(1);
 expect(writes[0].participant_plans).toEqual([
  {member:'member-1',spending_limit:'80,50',planned_share:'60'},
  {member:'member-2',spending_limit:null,planned_share:'40'},
 ]);
 await expect(planner.getByText('Freizeit',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);

 await planner.getByRole('button',{name:'Kostenbereich bearbeiten: Freizeit',exact:true}).click();
 const edit=page.getByRole('dialog',{name:'Kostenbereich bearbeiten'});
 const editParticipants=edit.locator('details.budget-participant-settings');
 await editParticipants.locator('summary').click();
 await expect(edit.getByLabel('Persönliches Limit · Alex (EUR)',{exact:true})).toHaveValue('80.50');
 await expect(edit.getByLabel('Geplanter Kostenanteil · Alex (EUR)',{exact:true})).toHaveValue('60.00');
 await expect(edit.getByLabel('Geplanter Kostenanteil · Sam (EUR)',{exact:true})).toHaveValue('40.00');
 await expect(edit.getByText(/keine Ausgabe, Schuld oder Abrechnung/)).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
});

test('finance · overall budget uses the same participant planning contract atomically',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true,language:'de'});
 const ledger={id:'ledger-home',family:'family-1',name:'Familie',base_currency:'EUR',budget_amount:'500.00',estimated_amount:null,is_default:true,archived:false,updated_at:'2026-10-14T11:00:00Z'};
 let plans=[];
 const writes=[];

 await page.route(/\/api\/expense-(?:ledgers|budgets)\//,async route=>{
  const request=route.request();
  const path=new URL(request.url()).pathname;
  const method=request.method();
  if(path==='/api/expense-ledgers/'&&method==='GET')return json(route,[ledger]);
  if(path==='/api/expense-ledgers/ledger-home/budget-summary/'&&method==='GET')return json(route,{
   family:'family-1',ledger:ledger.id,currency:'EUR',budget_amount:ledger.budget_amount,estimated_amount:ledger.estimated_amount,updated_at:ledger.updated_at,spent_amount:'0.00',reserved_amount:'0.00',remaining_amount:ledger.budget_amount,available_amount:ledger.budget_amount,over_budget:false,over_available:false,unconverted_expense_count:0,budgets:[],
  });
  if(path==='/api/expense-budgets/'&&method==='GET')return json(route,[]);
  if(path==='/api/expense-ledgers/ledger-home/participant-plans/'&&method==='GET')return json(route,{scope_type:'ledger',scope_id:'ledger-home',currency:'EUR',can_manage:true,plans});
  if(path==='/api/expense-ledgers/ledger-home/participant-plans/'&&method==='PATCH'){
   const body=request.postDataJSON();writes.push(body);
   ledger.budget_amount=normalize(body.budget_amount);ledger.estimated_amount=normalize(body.estimated_amount);ledger.updated_at='2026-10-14T11:01:00Z';
   plans=(body.participant_plans||[]).map(row=>({member:row.member,member_name:row.member==='member-1'?'Alex':'Sam',spending_limit:normalize(row.spending_limit),planned_share:normalize(row.planned_share),spending_limit_visible:true}));
   return json(route,ledger);
  }
  return route.fallback();
 });

 await page.setViewportSize({width:390,height:844});
 await page.goto('/?page=expenses&ledger=ledger-home');
 await page.waitForLoadState('networkidle');
 const planner=page.getByRole('region',{name:'Budget',exact:true});
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Gesamtbudget planen'});
 const participants=dialog.locator('details.budget-participant-settings');
 await participants.locator('summary').click();
 await expect(dialog.getByLabel('Persönliches Limit · Alex (EUR)',{exact:true})).toBeVisible();
 await dialog.getByLabel('Persönliches Limit · Alex (EUR)',{exact:true}).fill('200,50');
 await dialog.getByLabel('Geplanter Kostenanteil · Alex (EUR)',{exact:true}).fill('250');
 await dialog.getByLabel('Geplanter Kostenanteil · Sam (EUR)',{exact:true}).fill('250');
 await dialog.getByRole('button',{name:'Budget speichern',exact:true}).click();

 expect(writes).toHaveLength(1);
 expect(writes[0].budget_amount).toBe('500.00');
 expect(writes[0].participant_plans).toEqual([
  {member:'member-1',spending_limit:'200,50',planned_share:'250'},
  {member:'member-2',spending_limit:null,planned_share:'250'},
 ]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);

 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 const reopened=page.getByRole('dialog',{name:'Gesamtbudget planen'});
 await reopened.locator('details.budget-participant-settings summary').click();
 await expect(reopened.getByLabel('Persönliches Limit · Alex (EUR)',{exact:true})).toHaveValue('200.50');
 await expect(reopened.getByLabel('Geplanter Kostenanteil · Alex (EUR)',{exact:true})).toHaveValue('250.00');
 await expect(reopened.getByLabel('Geplanter Kostenanteil · Sam (EUR)',{exact:true})).toHaveValue('250.00');
});
