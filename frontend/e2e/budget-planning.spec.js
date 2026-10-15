import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

async function boot(page,{ledger='ledger-home',standalone=false,language='de'}={}){
 if(standalone)await page.addInitScript(()=>Object.defineProperty(navigator,'standalone',{value:true,configurable:true}));
 await installApiMocks(page,{dismissOnboarding:true,language});
 const store={
  ledgers:['home','trip'].map((name,index)=>({id:`ledger-${name}`,family:'family-1',name:index?'Japan':'Familie',base_currency:'EUR',budget_amount:null,estimated_amount:null,is_default:!index,archived:false,updated_at:'2026-10-14T10:00:00Z'})),
  budgets:[],writes:[],version:0,rejectOnce:false,loseResponseOnce:false,summaryFails:false,
 };
 const revision=()=>`2026-10-14T10:00:${String(++store.version).padStart(2,'0')}Z`;
 const fixed=value=>value===null?null:Number(String(value).replace(',','.')).toFixed(2);
 await page.route(/\/api\/expense-(?:ledgers|budgets)\//,async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname;const method=request.method();
  if(path==='/api/expense-ledgers/'&&method==='GET')return json(route,store.ledgers);
  const summary=path.match(/^\/api\/expense-ledgers\/([^/]+)\/budget-summary\/$/);
  if(summary){
   if(store.summaryFails)return json(route,{detail:'Unavailable'},503);
   const row=store.ledgers.find(item=>item.id===summary[1]);
   return json(route,{...row,ledger:row.id,currency:'EUR',spent_amount:'10.00',remaining_amount:row.budget_amount===null?null:(Number(row.budget_amount)-10).toFixed(2),over_budget:row.budget_amount!==null&&Number(row.budget_amount)<10,unconverted_expense_count:0,budgets:store.budgets.filter(item=>item.ledger===row.id&&!item.archived)});
  }
  if(path==='/api/expense-budgets/'&&method==='GET')return json(route,store.budgets.filter(item=>!item.archived&&(!url.searchParams.get('ledger')||item.ledger===url.searchParams.get('ledger'))));
  const ledgerMatch=path.match(/^\/api\/expense-ledgers\/([^/]+)\/$/);
  const budgetMatch=path.match(/^\/api\/expense-budgets\/([^/]+)\/$/);
  if(method==='PATCH'||method==='POST'){
   const body=request.postDataJSON();store.writes.push({path,body,method});
   if(store.rejectOnce){store.rejectOnce=false;return json(route,{estimated_amount:['Bitte Schätzung prüfen.']},400)}
   let row=ledgerMatch?store.ledgers.find(item=>item.id===ledgerMatch[1]):budgetMatch?store.budgets.find(item=>item.id===budgetMatch[1]):null;
   if(row&&body.expected_updated_at&&body.expected_updated_at!==row.updated_at)return json(route,{detail:'Conflict'},409);
   if(!row){
    row=store.budgets.find(item=>item.client_request_id===body.client_request_id&&item.ledger===body.ledger);
    if(row){
     if(row.name!==body.name||row.amount!==fixed(body.amount)||row.estimated_amount!==fixed(body.estimated_amount))return json(route,{detail:'Conflict'},409);
     return json(route,row,201);
    }
    row={id:`budget-${store.budgets.length+1}`,spent_amount:'0.00',archived:false,parent:null,currency:'EUR'};store.budgets.push(row);
   }
   Object.assign(row,body,{updated_at:revision()});
   for(const key of ['budget_amount','amount','estimated_amount'])if(key in body)row[key]=fixed(body[key]);
   if(row.amount!==undefined){row.remaining_amount=row.amount;row.over_budget=false}
   if(store.loseResponseOnce){store.loseResponseOnce=false;return route.abort('failed')}
   return json(route,row,method==='POST'?201:200);
  }
  return route.fallback();
 });
 await page.goto(`/?page=expenses&ledger=${ledger}`);
 const planner=page.getByRole('dialog',{name:/Gesamtbudget planen|Kostenbereich|Plan overall budget|cost category/i}).or(page.getByRole('region',{name:'Budget',exact:true}));
 await expect(planner.getByRole('button',{name:/^(Budget planen|Plan budget)$/})).toBeEnabled();
 return {store,planner};
}

async function openCategories(planner){
 await expect(planner.getByRole('button',{name:'Budget planen',exact:true})).toBeEnabled();
 const details=planner.locator('details');
 if(await details.getAttribute('open')===null)await details.locator('summary').click();
 await expect(details).toHaveAttribute('open','');
}

test('budget planning · estimate, plan and actual stay distinct without expense writes',async({page})=>{
 const {store,planner}=await boot(page);
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 await planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true}).fill('1250,50');
 await planner.getByLabel('Schätzung (optional) (EUR)',{exact:true}).fill('1400,75');
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner).toContainText('1.250,50');
 await expect(planner).toContainText('1.400,75');
 await expect(planner).toContainText('10,00');
 await expect(planner.getByRole('button',{name:'Budget planen',exact:true})).toBeFocused();
 expect(store.writes).toHaveLength(1);
 expect(store.writes[0].path).toBe('/api/expense-ledgers/ledger-home/');
 expect(store.writes[0].body.expected_updated_at).toBe('2026-10-14T10:00:00Z');
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 await planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true}).fill('');
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner).toContainText('Noch offen');
 expect(store.ledgers[0].budget_amount).toBeNull();
});

test('budget planning · English labels use the same canonical money editor',async({page})=>{
 const {store,planner}=await boot(page,{language:'en'});
 await planner.getByRole('button',{name:'Plan budget',exact:true}).click();
 await planner.getByLabel('Planned overall budget (EUR)',{exact:true}).fill('1250.25');
 await planner.getByLabel('Estimate (optional) (EUR)',{exact:true}).fill('1500.50');
 await planner.getByRole('button',{name:'Save budget',exact:true}).click();
 await expect(planner).toContainText('1,250.25');
 await expect(planner).toContainText('1,500.50');
 expect(store.ledgers[0].budget_amount).toBe('1250.25');
});

test('budget planning · category lost-response retry is idempotent, then edit and archive',async({page})=>{
 const {store,planner}=await boot(page,{ledger:'ledger-trip'});
 await openCategories(planner);
 await planner.getByRole('button',{name:'Kostenbereich hinzufügen',exact:true}).click();
 await planner.getByRole('textbox',{name:'Kostenbereich',exact:true}).fill('Unterkunft');
 await planner.getByRole('textbox',{name:'Geplant (EUR)',exact:true}).fill('800');
 await planner.getByLabel('Schätzung (optional) (EUR)',{exact:true}).fill('900,50');
 store.loseResponseOnce=true;
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner.getByRole('alert')).toBeVisible();
 await expect(planner.getByRole('textbox',{name:'Kostenbereich',exact:true})).toHaveValue('Unterkunft');
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner.getByRole('heading',{name:'Budget',exact:true})).toBeVisible();
 expect(store.budgets).toHaveLength(1);
 expect(store.writes[0].body.client_request_id).toBe(store.writes[1].body.client_request_id);
 expect(store.budgets[0].ledger).toBe('ledger-trip');
 await openCategories(planner);
 await planner.getByRole('button',{name:'Kostenbereich bearbeiten: Unterkunft',exact:true}).click();
 await planner.getByRole('textbox',{name:'Geplant (EUR)',exact:true}).fill('850,25');
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await openCategories(planner);
 await expect(planner).toContainText('850,25');
 await planner.getByRole('button',{name:'Archivieren: Unterkunft',exact:true}).click();
 await page.getByRole('alertdialog').getByRole('button',{name:'Archivieren',exact:true}).click();
 await expect(planner.getByText('Unterkunft',{exact:true})).toHaveCount(0);
 expect(store.budgets[0].archived).toBe(true);
 await expect(planner.getByRole('button',{name:'Kostenbereich hinzufügen',exact:true})).toBeFocused();
});

test('budget planning · validation and server errors retain input with field errors',async({page})=>{
 const {store,planner}=await boot(page);
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 const plan=planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true});
 const estimate=planner.getByLabel('Schätzung (optional) (EUR)',{exact:true});
 await plan.fill('12.345');
 await estimate.fill('55,25');
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(plan).toHaveAttribute('aria-invalid','true');
 expect(store.writes).toHaveLength(0);
 await plan.fill('100');store.rejectOnce=true;
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(estimate).toHaveAttribute('aria-invalid','true');
 await expect(estimate).toHaveValue('55,25');
 await expect(plan).toHaveValue('100');
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner).toContainText('100,00');
});

test('budget planning · stale revision requires deliberate reload without silent overwrite',async({page})=>{
 const {store,planner}=await boot(page);
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 await planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true}).fill('200');
 Object.assign(store.ledgers[0],{budget_amount:'350.00',updated_at:'2026-10-14T10:01:00Z'});
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner.getByRole('alert')).toContainText('Deine Eingaben bleiben erhalten');
 await expect(planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true})).toHaveValue('200');
 await expect(planner.getByRole('button',{name:'Budget speichern',exact:true})).toHaveCount(0);
 await planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true}).fill('201');
 await expect(planner.getByRole('alert')).toContainText('Deine Eingaben bleiben erhalten');
 await planner.getByRole('button',{name:'Aktuellen Stand laden',exact:true}).click();
 await expect(planner).toContainText('350,00');
 expect(store.ledgers[0].budget_amount).toBe('350.00');
});

test('budget planning · Escape closes editor and account switch preserves linked context',async({page})=>{
 const {store,planner}=await boot(page,{ledger:'ledger-trip'});
 await expect(planner).toContainText('Japan');
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 await planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true}).fill('200');
 await page.keyboard.press('Escape');
 await expect(planner.getByRole('button',{name:'Budget planen',exact:true})).toBeFocused();
 await page.locator('.expenses-toolbar').getByRole('combobox',{name:'Konto',exact:true}).selectOption('ledger-home');
 await expect(planner.getByRole('heading',{name:'Budget',exact:true})).toBeVisible();
 await expect(planner).toContainText('Familie');
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 await expect(planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true})).toHaveValue('');
 expect(store.writes).toHaveLength(0);
 await expect(page).toHaveURL(/ledger=ledger-home/);
});

test('budget planning · loading failure is visible and retry restores planner',async({page})=>{
 const {store,planner}=await boot(page);
 store.summaryFails=true;
 await page.reload();
 await expect(planner).toContainText('Budgetplanung konnte nicht geladen werden');
 await expect(planner.getByRole('button',{name:'Budget planen',exact:true})).toBeDisabled();
 store.summaryFails=false;
 await planner.getByRole('button',{name:'Erneut laden',exact:true}).click();
 await expect(planner.getByRole('button',{name:'Budget planen',exact:true})).toBeEnabled();
});

test('budget planning · offline input is retained without a finance write',async({page,context})=>{
 const {store,planner}=await boot(page);
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 await planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true}).fill('200');
 await context.setOffline(true);
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner.getByRole('alert')).toContainText('offline');
 await expect(planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true})).toHaveValue('200');
 expect(store.writes).toHaveLength(0);
 await context.setOffline(false);
});

test('budget planning · responsive and standalone keyboard flow stays within the viewport',async({page},testInfo)=>{
 const {planner}=await boot(page,{standalone:true});
 await page.emulateMedia({reducedMotion:'reduce'});
 for(const viewport of [{width:320,height:568},{width:390,height:844},{width:844,height:390},{width:1024,height:768},{width:1440,height:900},{width:1920,height:1080}]){
  await page.setViewportSize(viewport);
  await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
  const plan=planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true});
  await expect(plan).toBeFocused();
  await page.keyboard.type('1234,50');
  await page.keyboard.press('Tab');
  await expect(planner.getByLabel('Schätzung (optional) (EUR)',{exact:true})).toBeFocused();
  await page.keyboard.type('1400');
  await planner.scrollIntoViewIfNeeded();
  await expect(page.locator('.global-create-fab')).not.toBeVisible();
  const bounds=await planner.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(viewport.width+1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await planner.screenshot({path:testInfo.outputPath(`budget-editor-${viewport.width}.png`)});
  await planner.getByRole('button',{name:'Schließen',exact:true}).click();
  await expect(planner.getByRole('button',{name:'Budget planen',exact:true})).toBeFocused();
 }
 // 1440x900 at 200% browser zoom has a 720x450 CSS layout viewport.
 await page.setViewportSize({width:720,height:450});
 await planner.getByRole('button',{name:'Budget planen',exact:true}).click();
 await planner.getByLabel('Geplantes Gesamtbudget (EUR)',{exact:true}).fill('250');
 await planner.getByRole('button',{name:'Budget speichern',exact:true}).click();
 await expect(planner).toContainText('250,00');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
 await planner.screenshot({path:testInfo.outputPath('budget-overview-zoom-layout.png')});
});
