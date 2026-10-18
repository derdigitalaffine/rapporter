import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';

async function children(page,{language='de'}={}){
 const app=await installApiMocks(page,{language});
 const full={can_log_care:true,can_view_growth_development:true,can_manage_account:true,can_manage_care_circle:true,is_guardian:true,source:'custody'};
 const babies=[{id:'older',family:'family-1',membership:'child-1',display_name:'Robin',birth_date:'2018-03-12',permissions:full},
  {id:'younger',family:'family-1',membership:'child-2',display_name:'Kim',birth_date:new Date(Date.now()-60*86400000).toISOString().slice(0,10),permissions:{can_log_care:true,can_view_growth_development:false,can_manage_account:false,is_guardian:false,source:'care_circle'}}];
 const writes=[];
 let failSave=false;
 const records=[{key:'exam:U9',kind:'exam',title:'U9',state:'unknown',historical:true,version:0,reference:{}},
  {key:'exam:J1',kind:'exam',title:'J1',state:'unknown',historical:false,version:0,reference:{}}];
 await page.route('**/api/baby/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname.replace('/api',''),method=request.method();
  const json=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  if(path==='/baby/module/')return json({enabled:true,authorized:true,can_manage:true,can_record_custody_on_create:true,permissions:{...full,can_view_pregnancy:false}});
  if(path==='/baby/profiles/')return json({babies});
  if(path==='/baby/health-events/event-private/')return json({family:'family-1',baby:'older'});
  if(path==='/baby/profiles/older/health/'){
   if(method==='POST'){
    const body=request.postDataJSON();writes.push({path,body});
    if(failSave)return json({detail:'Speichern fehlgeschlagen'},503);
    for(const value of body.entries||[body]){const row=records.find(row=>row.key===value.key);if(row)Object.assign(row,value,{version:row.version+1})}
   }
   return json({items:records,vaccination_reference_available:false});
  }
  if(path==='/baby/profiles/older/care-circle/'){
   if(method==='PUT')writes.push({path,body:request.postDataJSON()});
   return json({authorities:[{membership:'member-1',display_name:'Alex',has_custody:true}],care_circle:[],inherited:[]});
  }
  if(path==='/baby/profiles/younger/care/')return json({events:[],summary:{counts:{},totals:{},last:{}}});
  if(path.endsWith('/viewed/'))return json({});
  if(method!=='GET')writes.push({path,body:request.postDataJSON()});
  return json({});
 });
 await page.route('**/api/auth/reauth/password/',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
 return {app,writes,fail:()=>{failSave=true}};
}

test('older child starts with neutral health history; sibling switch preserves scoped rights',async({page})=>{
 const {writes}=await children(page);
 await page.goto('/?page=baby');
 await expect(page.getByRole('heading',{name:'Vorsorge & Impfungen',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:/J1 Nicht dokumentiert/})).toBeVisible();
 expect(writes).toHaveLength(0);
 await page.getByRole('button',{name:'Bisheriger Stand',exact:true}).click();
 await expect(page.getByRole('button',{name:/U9 Nicht dokumentiert/})).toBeVisible();
 await page.getByLabel('Kind auswählen').selectOption('younger');
 await expect(page.locator('.baby-quick-grid')).toBeVisible();
 await expect(page.getByRole('button',{name:'Vorsorge & Impfungen',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Mehr',exact:true}).click();
 await expect(page.getByRole('button',{name:'Care Circle bearbeiten'})).toHaveCount(0);
 await page.goBack();
 await expect(page.locator('.baby-quick-grid')).toBeVisible();
});

test('custodian sees full access and can delegate without a Guardian switch',async({page})=>{
 const {writes}=await children(page);
 await page.goto('/?page=baby&baby=older&view=more');
 await expect(page.getByText('Sorgeberechtigt · Voller Zugriff')).toBeVisible();
 await page.getByRole('button',{name:'Care Circle bearbeiten'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByRole('checkbox',{name:/Guardian|Sorgeberechtigt/})).toHaveCount(0);
 await dialog.getByRole('checkbox',{name:'Pflege erfassen'}).check();
 await dialog.getByLabel('Dein aktuelles Passwort').fill('fixture-password');
 await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(dialog).toHaveCount(0);
 expect(writes.at(-1).body.care_circle).toContainEqual({membership:'member-2',can_log_care:true,can_view_growth_development:false});
});

test('health editor retains input after failure and confirms dirty dismissal',async({page})=>{
 const fixture=await children(page);fixture.fail();
 await page.goto('/?page=baby&baby=older&view=health');
 await page.getByRole('button',{name:'Impfung dokumentieren'}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByLabel('Impfung / Impfstoff').fill('Dokumentierter Impfstoff');
 await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(dialog.getByRole('alert')).toContainText('Speichern fehlgeschlagen');
 await expect(dialog.getByLabel('Impfung / Impfstoff')).toHaveValue('Dokumentierter Impfstoff');
 await dialog.getByRole('button',{name:'Abbrechen',exact:true}).click();
 await page.getByRole('button',{name:'Weiter bearbeiten',exact:true}).click();
 await expect(dialog.getByLabel('Impfung / Impfstoff')).toHaveValue('Dokumentierter Impfstoff');
});

test('historical completion is explicit and sends no appointment date',async({page})=>{
 const {writes}=await children(page);
 await page.goto('/?page=baby&baby=older&view=health');
 await page.getByRole('button',{name:'Bisheriger Stand',exact:true}).click();
 await page.getByRole('button',{name:'Bisherigen Stand ergänzen'}).click();
 await page.getByRole('checkbox',{name:'Erledigt: U9',exact:true}).check();
 await page.getByRole('button',{name:/Ausgewählte als erledigt dokumentieren/}).click();
 await expect.poll(()=>writes.length).toBe(1);
 expect(writes[0].body.entries).toEqual([expect.objectContaining({key:'exam:U9',state:'done',expected_version:0})]);
 expect(writes[0].body.entries[0].planned_at).toBeUndefined();
});

test('unavailable child link never falls back to a sibling',async({page})=>{
 await children(page);
 await page.goto('/?page=baby&baby=unavailable&view=health');
 await expect(page.getByRole('alert')).toContainText('kein freigegebenes Kind');
 await expect(page.getByRole('heading',{name:'Vorsorge & Impfungen',exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Kind auswählen')).toHaveValue('');
});

for(const width of [320,390,1024,1440])test(`health event link, English labels, axe and overflow at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:844});
 await page.emulateMedia({reducedMotion:'reduce'});
 await children(page,{language:'en'});
 await page.goto('/?page=baby&event=event-private&view=health');
 await expect(page.getByRole('heading',{name:'Check-ups & vaccinations',exact:true})).toBeVisible();
 await expect(page.getByLabel('Select child')).toHaveValue('older');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const result=await new AxeBuilder({page}).include('.baby-page').analyze();
 expect(result.violations).toEqual([]);
 await page.screenshot({path:test.info().outputPath(`children-${width}.png`),fullPage:true});
});
