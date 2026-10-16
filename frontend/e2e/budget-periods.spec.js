import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

test('finance · period and carryover stay progressive inside the existing budget editor',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true,language:'de'});
 const ledger={id:'ledger-home',family:'family-1',name:'Familie',base_currency:'EUR',budget_amount:null,estimated_amount:null,is_default:true,archived:false,updated_at:'2026-10-14T10:00:00Z'};
 const budgets=[];
 const writes=[];

 await page.route(/\/api\/expense-(?:ledgers|budgets)\//,async route=>{
  const request=route.request();
  const url=new URL(request.url());
  const path=url.pathname;
  const method=request.method();
  if(path==='/api/expense-ledgers/'&&method==='GET')return json(route,[ledger]);
  if(path==='/api/expense-ledgers/ledger-home/budget-summary/'&&method==='GET')return json(route,{
   ...ledger,ledger:ledger.id,currency:'EUR',spent_amount:'0.00',reserved_amount:'0.00',remaining_amount:null,available_amount:null,over_budget:false,over_available:false,unconverted_expense_count:0,budgets,
  });
  if(path==='/api/expense-budgets/'&&method==='GET')return json(route,budgets);
  if(path==='/api/expense-budgets/'&&method==='POST'){
   const body=request.postDataJSON();writes.push(body);
   const row={
    id:'budget-1',family:'family-1',ledger:'ledger-home',parent:null,name:body.name,amount:Number(String(body.amount).replace(',','.')).toFixed(2),estimated_amount:null,currency:'EUR',period_type:body.period_type,
    rollover_policy:body.rollover_policy||null,period_starts_on:'2026-10-01',period_ends_on:'2026-10-31',starts_on:body.starts_on||null,ends_on:body.ends_on||null,carryover_amount:'25.00',spent_amount:'50.00',reserved_amount:'10.00',remaining_amount:'50.00',available_amount:'65.00',over_budget:false,over_available:false,archived:false,updated_at:'2026-10-14T10:01:00Z',
   };
   budgets.push(row);return json(route,row,201);
  }
  const match=path.match(/^\/api\/expense-budgets\/([^/]+)\/$/);
  if(match&&method==='PATCH'){
   const row=budgets.find(item=>item.id===match[1]);Object.assign(row,request.postDataJSON(),{updated_at:'2026-10-14T10:02:00Z'});return json(route,row);
  }
  return route.fallback();
 });

 await page.setViewportSize({width:390,height:844});
 await page.goto('/?page=expenses&ledger=ledger-home');
 await page.waitForLoadState('networkidle');
 const planner=page.getByRole('region',{name:'Budget',exact:true});
 const categories=planner.locator('details.finance-collapsible').first();
 if(await categories.getAttribute('open')===null)await categories.locator(':scope > summary').click();
 await planner.getByRole('button',{name:'Kostenbereich hinzufügen',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Kostenbereich hinzufügen'});
 await dialog.getByRole('textbox',{name:'Kostenbereich',exact:true}).fill('Freizeit');
 await dialog.getByRole('textbox',{name:'Geplant (EUR)',exact:true}).fill('100');

 const period=dialog.locator('details.budget-period-settings');
 await expect(period.getByText('Zeitraum & Übertrag',{exact:true})).toBeVisible();
 await expect(period).not.toHaveAttribute('open','');
 await period.locator('summary').click();
 const periodSelect=dialog.getByLabel('Budgetzeitraum',{exact:true});
 await expect(periodSelect.locator('option[value="context"]')).toHaveCount(0);
 await periodSelect.selectOption('month');
 await expect(dialog.getByLabel('Am Periodenende',{exact:true})).toBeVisible();
 await dialog.getByLabel('Am Periodenende',{exact:true}).selectOption('carry_positive');
 await expect(dialog.getByText(/Aktive Vormerkungen bleiben erhalten/)).toBeVisible();
 await dialog.getByRole('button',{name:'Budget speichern',exact:true}).click();

 expect(writes).toHaveLength(1);
 expect(writes[0].period_type).toBe('month');
 expect(writes[0].rollover_policy).toBe('carry_positive');
 expect(writes[0].starts_on).toBeNull();
 expect(writes[0].ends_on).toBeNull();

 await expect(planner).toContainText('Übertrag: 25,00');
 await expect(planner).toContainText('Aktueller Zeitraum:');
 await expect(planner).toContainText('Monatlich');
 await expect(planner).toContainText('Verfügbar: 65,00');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);

 await planner.getByRole('button',{name:'Kostenbereich bearbeiten: Freizeit',exact:true}).click();
 const edit=page.getByRole('dialog',{name:'Kostenbereich bearbeiten'});
 await edit.locator('details.budget-period-settings summary').click();
 await expect(edit.getByLabel('Budgetzeitraum',{exact:true})).toHaveValue('month');
 await expect(edit.getByLabel('Am Periodenende',{exact:true})).toHaveValue('carry_positive');
});
