import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';

async function setup(page,{pregnancyAccess=true}={}){
 await installApiMocks(page,{language:'de'});
 const pregnancy={id:'pregnancy-1',status:'active',expected_due_date:'2027-01-02',progress:{week:28,day:3,days_until_due:81},babies:[{id:'expected-1',stable_label:'A',display_name:'Baby'}]};
 const permissions={can_log_care:true,can_view_growth_development:true,can_manage_account:true,is_guardian:true,source:'custody'};
 const module={enabled:true,authorized:true,can_manage:true,show_in_main_navigation:false,permissions:{...permissions,can_view_pregnancy:pregnancyAccess},active_pregnancy:pregnancyAccess?pregnancy:null};
 const writes=[];let failed=false;
 const items=[{key:'exam:U6',kind:'exam',title:'U6',state:'unknown',version:0,historical:false,window_start:'2027-01-02',window_end:'2027-02-03'},
  ...[1,2].map(dose=>({key:`vaccination:test:${dose}`,kind:'vaccination',title:'Synthetische Testreferenz',dose,state:'unknown',version:0,historical:false,window_start:'2027-01-02',window_end:'2027-02-03',reference:{checksum:'a'.repeat(64)}}))];
 await page.route('**/api/baby/**',route=>{
  const request=route.request(),path=new URL(request.url()).pathname.replace('/api','');
  const json=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  if(request.method()!=='GET')writes.push({path,body:request.postDataJSON()});
  if(path==='/baby/module/')return json(module);
  if(path==='/baby/profiles/')return json({babies:[{id:'child-1',family:'family-1',display_name:'Robin',birth_date:'2018-01-02',permissions}]});
  if(path==='/baby/pregnancies/')return json({pregnancies:[pregnancy]});
  if(path.endsWith('/birth-preferences/'))return json({birth_preferences:''});
  if(path.endsWith('/utilities/'))return json({sessions:[]});
  if(path.endsWith('/health/reminders/')){
   if(!failed){failed=true;return json({detail:'Erneut versuchen'},503)}
   items.filter(row=>request.postDataJSON().entries.some(entry=>entry.key===row.key)).forEach(row=>{row.reminder={task:'reminder-task',due_at:request.postDataJSON().remind_at,completed:false};row.version++});
   return json({});
  }
  if(path.endsWith('/health/'))return json({items,vaccination_reference_available:true,vaccination_reference:{title:'Synthetische Testreferenz',version:'Teststand 1',effective_from:'2026-01-02'}});
  return json({});
 });
 return {module,writes,pregnancy};
}

test('two menu entries and hierarchical back preserve pregnancy functions',async({page})=>{
 await setup(page);
 await page.goto('/?page=more');
 const main=page.getByRole('main');
 await expect(main.getByRole('button',{name:'Kinder',exact:true})).toBeVisible();
 await main.getByRole('button',{name:'Schwangerschaft',exact:true}).click();
 await expect(page.locator('.baby-page h1')).toHaveText('Schwangerschaft');
 await expect(page.locator('.pregnancy-status')).toContainText('02.01.2027');
 await expect(page.getByLabel('Kind auswählen')).toHaveCount(0);
 const nav=page.getByRole('navigation',{name:'Schwangerschaft',exact:true});
 await nav.getByRole('button',{name:'Hinzufügen',exact:true}).click();
 await page.getByRole('button',{name:'Termin',exact:true}).click();
 await expect(page.getByLabel('Terminbezeichnung')).toBeVisible();
 await nav.getByRole('button',{name:'Mehr',exact:true}).click();
 await expect(page.getByText('Geburtswünsche',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Zurück zur Übersicht',exact:true}).click();
 await expect(page.locator('.pregnancy-status')).toBeVisible();
 await page.getByRole('button',{name:'Zurück zu Mehr',exact:true}).click();
 await expect(page).toHaveURL(/page=more/);
});

test('legacy pregnancy selector resolves and new navigation uses the separate route',async({page})=>{
 await setup(page);
 await page.goto('/?page=baby&view=pregnancy');
 await expect(page.locator('.pregnancy-status')).toBeVisible();
 await page.getByRole('navigation',{name:'Schwangerschaft',exact:true}).getByRole('button',{name:'Mehr',exact:true}).click();
 await expect(page).toHaveURL(/page=pregnancy.*view=more/);
});

test('vaccination selections are explicit, failed reminder retains date and successful retry links canonical task',async({page})=>{
 const {writes}=await setup(page);
 await page.goto('/?page=baby&view=health');
 await expect(page.getByRole('button',{name:/U6.*02.01.2027.*03.02.2027/})).toBeVisible();
 await page.getByRole('button',{name:'Impfkalender',exact:true}).click();
 await expect(page.locator('.child-reference')).toContainText('Teststand 1');
 await expect(page.locator('.child-reference')).toContainText('02.01.2026');
 await page.getByRole('button',{name:'An Impfungen erinnern',exact:true}).click();
 const checks=page.getByRole('checkbox',{name:/Für Erinnerung auswählen/});
 await expect(checks).toHaveCount(2);
 await expect(checks.nth(0)).not.toBeChecked();await expect(checks.nth(1)).not.toBeChecked();
 expect(writes).toHaveLength(0);
 await checks.nth(0).check();await checks.nth(1).check();
 await page.getByRole('button',{name:'Aufgaben anlegen (2)',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'An Impfungen erinnern',exact:true});
 const date=dialog.getByLabel(/An Terminvereinbarung erinnern am/);
 await date.fill('2030-01-02T10:30');
 await dialog.getByRole('button',{name:'Aufgaben anlegen',exact:true}).click();
 await expect(dialog.getByRole('alert')).toHaveText('Erneut versuchen');
 await expect(date).toHaveValue('2030-01-02T10:30');
 await dialog.getByRole('button',{name:'Aufgaben anlegen',exact:true}).click();
 await expect(dialog).toHaveCount(0);
 await expect(page.getByRole('link',{name:/Erinnerungsaufgabe/})).toHaveCount(2);
 expect(writes).toHaveLength(2);expect(writes[1]).toEqual(writes[0]);
 expect(writes[0].body.entries).toHaveLength(2);
 expect(JSON.stringify(writes[0].body)).not.toContain('Robin');
});

test('pregnancy widget is opt-in and disappears on revoked pregnancy permission',async({page})=>{
 const {module}=await setup(page);
 await page.goto('/');
 await expect(page.locator('.today-pregnancy-widget')).toHaveCount(0);
 await page.getByRole('button',{name:'Anpassen',exact:true}).click();
 const add=page.locator('[data-library-widget="pregnancy"]');
 // The editor consumes the same gated registry; the stored layout is unchanged until Save.
 const library=page.locator('.today-layout-editor');
 await expect(library.getByText('Schwangerschaft',{exact:true})).toBeVisible();
 await add.getByRole('button',{name:'Hinzufügen',exact:true}).click();
 await library.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(page.locator('.today-pregnancy-widget')).toContainText('02.01.2027');
 module.permissions.can_view_pregnancy=false;module.active_pregnancy=null;
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await expect(page.locator('.today-pregnancy-widget')).toHaveCount(0);
});

for(const width of [320,390,1024,1440])test(`pregnancy overview and vaccine UI are accessible at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:844});await page.emulateMedia({reducedMotion:'reduce'});
 await setup(page);await page.goto('/?page=pregnancy');
 await expect(page.locator('.pregnancy-status')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect((await new AxeBuilder({page}).include('.baby-page').analyze()).violations).toEqual([]);
 await page.screenshot({path:test.info().outputPath(`pregnancy-${width}.png`),fullPage:true});
 await page.goto('/?page=baby&view=health');await page.getByRole('button',{name:'Impfkalender',exact:true}).click();
 await expect(page.locator('.child-reference')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect((await new AxeBuilder({page}).include('.baby-page').analyze()).violations).toEqual([]);
 await page.screenshot({path:test.info().outputPath(`vaccinations-${width}.png`),fullPage:true});
});
