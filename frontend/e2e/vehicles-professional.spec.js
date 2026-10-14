import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api';

function journey(overrides={}){
 const endedAt=new Date(Date.now()-3600000).toISOString();
 return {
  id:'trip-1',vehicle:'car-1',created_at:endedAt,updated_at:endedAt,
  started_at:new Date(Date.now()-7200000).toISOString(),ended_at:endedAt,
  start_odometer:'100.0',end_odometer:'110.0',purpose:'',kind:'unclassified',
  destination:'',business_partner:'',note:'',detour_reason:'',source:'tracked',
  review_due_at:new Date(Date.now()+6*86400000).toISOString(),classified_at:null,
  voided_at:null,void_reason:'',legacy_record:false,review_locked:false,needs_review:true,
  distance_m:9800,point_count:0,...overrides,
 };
}

async function setup(page,{language='de'}={}){
 await installApiMocks(page,{language});
 const car={id:'car-1',family:'family-1',name:'Familienauto',plate:'B-OS 2026',manufacturer:'VW',model:'Golf',fuel_type:'petrol',odometer:'110.0',vin:'',first_registration:null,notes:'',archived:false};
 const state={cars:[car],fuel:[],journeys:[journey()],revisions:[],manualCreates:0};
 const report=()=>{
  const visible=state.journeys.filter(row=>!row.voided_at);
  const byKind={business:0,private:0,commute:0,unclassified:0};let open=0,total=0;
  for(const row of visible){const km=Number(row.end_odometer)-Number(row.start_odometer);byKind[row.kind]+=km;total+=km;if(row.needs_review)open++}
  return {summary:{count:visible.length,open_review:open,distance_km:total.toFixed(1),by_kind_km:Object.fromEntries(Object.entries(byKind).map(([key,value])=>[key,value.toFixed(1)]))}};
 };
 const json=(route,payload,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(payload)});
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  if(!path.startsWith('/api/vehicles/')&&!path.startsWith('/api/vehicle-journeys/'))return route.fallback();
  if(path==='/api/vehicles/'&&method==='GET')return json(route,state.cars);
  if(path==='/api/vehicles/active/'&&method==='GET')return json(route,null);
  if(path==='/api/vehicles/map-config/'&&method==='GET')return json(route,{configured:false});
  if(path==='/api/vehicles/car-1/fuel/'&&method==='GET')return json(route,state.fuel);
  if(path==='/api/vehicles/car-1/journeys/'&&method==='GET'){
   let rows=state.journeys.filter(row=>!row.voided_at);
   const review=url.searchParams.get('review');if(review==='open')rows=rows.filter(row=>row.needs_review);if(review==='done')rows=rows.filter(row=>!row.needs_review);
   const kind=url.searchParams.get('kind');if(kind)rows=rows.filter(row=>row.kind===kind);
   return json(route,rows);
  }
  if(path==='/api/vehicles/car-1/journey-report/'&&method==='GET'){
   const format=url.searchParams.get('format');
   if(format){
    const names={csv:'fahrtenbuch.csv',pdf:'fahrtenbuch.pdf',audit:'fahrtenbuch-audit.csv'};
    const content=format==='pdf'?'%PDF-1.4 professional test':'journey_id,kind\ntrip-1,business\n';
    return route.fulfill({status:200,contentType:format==='pdf'?'application/pdf':'text/csv;charset=utf-8',headers:{'Content-Disposition':`attachment; filename="${names[format]}"`},body:content});
   }
   let rows=state.journeys.filter(row=>!row.voided_at);
   const review=url.searchParams.get('review');if(review==='open')rows=rows.filter(row=>row.needs_review);
   const snapshot=report();if(review==='open')snapshot.summary={...snapshot.summary,count:rows.length,open_review:rows.filter(row=>row.needs_review).length};
   return json(route,snapshot);
  }
  if(path==='/api/vehicles/car-1/journey-suggestions/'&&method==='GET')return json(route,{destinations:['Berlin'],business_partners:['Beispiel GmbH'],purposes:['Projekttermin']});
  if(path==='/api/vehicle-journeys/trip-1/'&&method==='GET')return json(route,{...state.journeys[0],points:[]});
  if(path==='/api/vehicle-journeys/trip-1/classify/'&&method==='POST'){
   if(body.kind==='business'&&(!body.destination||!body.business_partner||!body.purpose))return json(route,{destination:['required_for_business'],business_partner:['required_for_business'],purpose:['required_for_business']},400);
   const current=state.journeys[0];state.revisions.push({event:current.needs_review?'classified':'corrected',reason:body.reason||'',before:{...current}});Object.assign(current,body,{needs_review:false,classified_at:new Date().toISOString()});return json(route,current);
  }
  if(path==='/api/vehicle-journeys/trip-1/correct/'&&method==='POST'){
   if(!body.reason)return json(route,{reason:['correction_reason_required']},400);const current=state.journeys[0];state.revisions.push({event:'corrected',reason:body.reason,before:{...current}});Object.assign(current,body);return json(route,current);
  }
  if(path==='/api/vehicle-journeys/trip-1/void/'&&method==='POST'){
   if(!body.reason)return json(route,{reason:['correction_reason_required']},400);const current=state.journeys[0];current.voided_at=new Date().toISOString();current.void_reason=body.reason;return json(route,current);
  }
  if(path==='/api/vehicles/car-1/journeys/manual/'&&method==='POST'){
   state.manualCreates++;const created=journey({...body,id:`manual-${state.manualCreates}`,source:'manual',legacy_record:false,review_due_at:new Date().toISOString(),classified_at:new Date().toISOString(),needs_review:false,distance_m:0,point_count:0});delete created.reason;state.journeys.unshift(created);car.odometer=String(body.end_odometer);return json(route,created,201);
  }
  return json(route,[]);
 });
 return state;
}

async function open(page){await page.goto('/?page=vehicles');await expect(page.getByRole('heading',{name:'Familienauto',exact:true})).toBeVisible()}

async function openFirstJourney(page){const details=page.locator('.vehicle-list details').first();await details.locator('summary').click();return details}

test('review inbox classifies a business journey with required details',async({page})=>{
 const state=await setup(page);await open(page);
 await expect(page.getByText('1 Fahrt(en) brauchen deine Zuordnung.')).toBeVisible();
 const details=await openFirstJourney(page);await details.getByRole('button',{name:'Fahrt zuordnen'}).click();
 await page.getByLabel('Fahrtart').selectOption('business');
 await expect(page.getByRole('button',{name:'Speichern'})).toBeVisible();
 await page.getByLabel('Ziel').fill('Berlin');
 await page.getByLabel('Geschäftspartner / Kunde').fill('Beispiel GmbH');
 await page.getByLabel('Konkreter geschäftlicher Zweck').fill('Projekttermin');
 await page.getByRole('button',{name:'Speichern'}).click();
 await expect(page.getByText('Alle angezeigten Fahrten sind zugeordnet.')).toBeVisible();
 expect(state.journeys[0].kind).toBe('business');expect(state.revisions).toHaveLength(1);expect(state.revisions[0].event).toBe('classified');
});

test('later correction requires a reason and keeps the journal entry',async({page})=>{
 const state=await setup(page);state.journeys=[journey({kind:'private',needs_review:false,classified_at:new Date().toISOString()})];await open(page);
 const details=await openFirstJourney(page);await details.getByRole('button',{name:'Fahrt korrigieren'}).click();
 await page.getByLabel('Kilometerstand bei Ende (km)').fill('111');
 await expect(page.getByRole('button',{name:'Speichern'})).toBeVisible();
 await page.getByLabel('Grund der Änderung').fill('Kilometerstand falsch abgelesen');
 await page.getByRole('button',{name:'Speichern'}).click();
 expect(state.journeys).toHaveLength(1);expect(state.journeys[0].end_odometer).toBe('111');expect(state.revisions[0].reason).toBe('Kilometerstand falsch abgelesen');
});

test('manual journey is explicit and reports download from the server',async({page})=>{
 const state=await setup(page);await open(page);
 await page.getByRole('button',{name:'Fahrt nachtragen'}).click();
 await page.getByLabel('Fahrtart').selectOption('business');
 await page.getByLabel('Kilometerstand bei Start (km)').fill('110');await page.getByLabel('Kilometerstand bei Ende (km)').fill('120');
 await page.getByLabel('Ziel').fill('Hamburg');await page.getByLabel('Geschäftspartner / Kunde').fill('Kunde Nord');await page.getByLabel('Konkreter geschäftlicher Zweck').fill('Workshop');
 await page.getByLabel('Grund der Änderung').fill('Browser war nicht verfügbar');
 await page.getByRole('button',{name:'Speichern'}).click();
 await expect(page.getByText('Manuell nachgetragen').first()).toBeVisible();expect(state.manualCreates).toBe(1);
 for(const [button,filename] of [['Fahrtenbuch als CSV','fahrtenbuch.csv'],['PDF-Bericht','fahrtenbuch.pdf'],['AuditLog als CSV','fahrtenbuch-audit.csv']]){
  const download=page.waitForEvent('download');await page.getByRole('button',{name:button}).click();expect((await download).suggestedFilename()).toBe(filename);
 }
});

test('professional logbook stays usable at 320px and passes axe',async({page})=>{
 await setup(page);await page.setViewportSize({width:320,height:844});await open(page);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const details=await openFirstJourney(page);await details.getByRole('button',{name:'Fahrt zuordnen'}).click();await page.getByLabel('Fahrtart').selectOption('business');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const result=await new AxeBuilder({page}).include('.journey-editor').analyze();expect(result.violations).toEqual([]);
});
