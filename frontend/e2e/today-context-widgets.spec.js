import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const FIXED_NOW='2026-10-10T10:00:00.000Z';
const TODAY='2026-10-10';
const TOMORROW='2026-10-11';
const familyOne={id:'family-1',name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-1',family:'family-1',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''}]};
const familyTwo={id:'family-2',name:'Nebenfamilie',slug:'nebenfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-2',family:'family-2',user:1,username:'alex',role:'adult',display_name:'Alex',avatar:''}]};

async function freezeToday(page){
 await page.addInitScript(now=>{const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[globalThis.__contextNow||now]))}static now(){return new RealDate(globalThis.__contextNow||now).getTime()} }},FIXED_NOW);
}
const action=(id,title,due,family='family-1',urgency='normal')=>({id:`task:${id}`,family,kind:'task',title,state:'open',due_at:due,next_due_at:due,completed_at:null,assignee:null,priority:urgency==='high'?'high':'normal',urgency,context:{source:'manual',list:{id:'list-1',name:'Alltag'},workflow:null},repeat:null,tags:[],primary_action:{id:'complete',method:'POST',href:`/api/tasks/${id}/toggle/`},allowed_actions:[],deep_link:`/?page=tasks&task=${id}`,ranking:{version:'actions-v1',bucket:urgency==='high'?1:5,reasons:['normal']}});
const event=(id,title,start,end,family='family-1',payload={provider:'FamilyOS'})=>({id,family,source:null,type:'calendar.event',title,starts_at:start,ends_at:end,actionable:false,payload});

async function boot(page,{visible=true}={}){
 await page.setViewportSize({width:390,height:844});await freezeToday(page);await installApiMocks(page,{dismissOnboarding:true});
 let layout={version:2,revision:0,widgets:[{id:'tomorrow',visible,size:'medium'},{id:'family-load',visible,size:'compact'}]};
 const requests={today:0,upcoming:0,tomorrowEvents:0};
 await page.route('**/api/today-layout/**',async route=>{
  if(route.request().method()==='PUT')layout={...route.request().postDataJSON(),revision:layout.revision+1};
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(layout)});
 });
 await page.route('**/api/actions/**',route=>{
  const scope=new URL(route.request().url()).searchParams.get('scope')||'today';requests[scope]=(requests[scope]||0)+1;
  const rows=scope==='upcoming'?[action('tomorrow-task','Sporttasche packen','2026-10-11T08:00:00.000Z'),action('later-task','Erst übermorgen','2026-10-12T08:00:00.000Z')]:[action('urgent','Rezept abholen','2026-10-10T13:00:00.000Z','family-1','high')];
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:rows.length,next:null,previous:null,results:rows,ranking_version:'actions-v1',scope})});
 });
 await page.route('**/api/events/**',route=>{
  const url=new URL(route.request().url());const start=url.searchParams.get('start');
  if(start===TOMORROW){requests.tomorrowEvents+=1;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([
   event('all-day','Schulfest',null,null,'family-1',{date_start:TOMORROW,date_end_exclusive:null,provider:'Schule'}),
   event('dentist','Zahnarzt morgen','2026-10-11T13:00:00.000Z','2026-10-11T14:00:00.000Z'),
   {id:'warning',family:'family-1',source:null,type:'public.warning',title:'Warnung morgen',starts_at:'2026-10-11T12:00:00.000Z',ends_at:'2026-10-11T15:00:00.000Z',payload:{provider:'Warnamt'}},
  ])})}
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([
   event('doctor','Kinderarzt','2026-10-10T12:00:00.000Z','2026-10-10T14:00:00.000Z'),
   event('parents','Elternabend','2026-10-10T13:00:00.000Z','2026-10-10T15:00:00.000Z'),
  ])});
 });
 await page.goto('/');await expect(page.getByRole('button',{name:'Anpassen'})).toBeEnabled();
 return {requests,getLayout:()=>layout};
}

test('Tomorrow uses the exact next civil day and Family Load shows concrete bottlenecks without a score',async({page})=>{
 const {requests}=await boot(page);
 const tomorrow=page.getByTestId('today-tomorrow');await expect(tomorrow).toBeVisible();
 await expect(tomorrow).toContainText('Schulfest');await expect(tomorrow).toContainText('Zahnarzt morgen');await expect(tomorrow).toContainText('Sporttasche packen');
 await expect(tomorrow).not.toContainText('Erst übermorgen');await expect(tomorrow).not.toContainText('Warnung morgen');
 const load=page.getByTestId('today-family-load');await expect(load).toContainText('Terminüberschneidung');await expect(load).toContainText('Kinderarzt überschneidet sich mit Elternabend');await expect(load).toContainText('1 dringendes Ding');await expect(load).not.toContainText(/Score|Punkte/i);
 await expect.poll(()=>requests.upcoming).toBe(1);await expect.poll(()=>requests.tomorrowEvents).toBe(1);await expect.poll(()=>requests.today).toBe(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
});

test('context widgets stay opt-in in the Library and persist only supported semantic sizes',async({page})=>{
 const {requests,getLayout}=await boot(page,{visible:false});
 await expect(page.getByTestId('today-tomorrow')).toHaveCount(0);await expect(page.getByTestId('today-family-load')).toHaveCount(0);expect(requests.upcoming).toBe(0);
 await page.getByRole('button',{name:'Anpassen'}).click();const editor=page.getByRole('region',{name:'Anpassen'});
 const tomorrowCard=editor.locator('[data-library-widget="tomorrow"]');const loadCard=editor.locator('[data-library-widget="family-load"]');
 await expect(tomorrowCard).toBeVisible();await expect(loadCard).toBeVisible();await expect(tomorrowCard.getByLabel('Unterstützte Größen')).toHaveText(/Kompakt.*Mittel/);await expect(tomorrowCard.getByLabel('Unterstützte Größen')).not.toContainText('Breit');
 await tomorrowCard.getByRole('button',{name:'Hinzufügen'}).click();await loadCard.getByRole('button',{name:'Hinzufügen'}).click();
 const tomorrowSize=editor.getByRole('combobox',{name:'Morgen · Größe'});await expect(tomorrowSize.locator('option')).toHaveText(['Kompakt','Mittel']);await tomorrowSize.selectOption('medium');
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 expect(getLayout().widgets.find(row=>row.id==='tomorrow')).toMatchObject({visible:true,size:'medium'});expect(getLayout().widgets.find(row=>row.id==='family-load')).toMatchObject({visible:true,size:'compact'});
 await expect(page.getByTestId('today-tomorrow')).toBeVisible();await expect(page.getByTestId('today-family-load')).toBeVisible();await expect.poll(()=>requests.upcoming).toBe(1);
});

test('late Tomorrow data from the previous family never flashes after a family switch',async({page})=>{
 await page.setViewportSize({width:390,height:844});await freezeToday(page);await installApiMocks(page,{dismissOnboarding:true});
 await page.route('**/api/families/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([familyOne,familyTwo])}));
 await page.route('**/api/today-layout/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:2,revision:0,widgets:[{id:'tomorrow',visible:true,size:'compact'}]})}));
 await page.route('**/api/actions/**',async route=>{
  const url=new URL(route.request().url());const family=url.searchParams.get('family');const scope=url.searchParams.get('scope')||'today';
  if(scope!=='upcoming')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:0,results:[],scope})});
  if(family==='family-1')await new Promise(resolve=>setTimeout(resolve,350));
  const rows=[action(family==='family-1'?'old':'new',family==='family-1'?'Alt-Familie morgen':'Nebenfamilie morgen','2026-10-11T08:00:00.000Z',family)];
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:1,results:rows,scope})});
 });
 await page.route('**/api/events/**',route=>route.fulfill({status:200,contentType:'application/json',body:'[]'}));
 await page.goto('/');const switcher=page.locator('.family-switcher select');await expect(switcher).toHaveValue('family-1');await switcher.selectOption('family-2');
 const tomorrow=page.getByTestId('today-tomorrow');await expect(tomorrow).toContainText('Nebenfamilie morgen');await page.waitForTimeout(450);await expect(tomorrow).not.toContainText('Alt-Familie morgen');
});

for(const [language,title,label] of [['fr','Demain','Ouvrir le calendrier'],['nl','Morgen','Kalender openen'],['th','พรุ่งนี้','เปิดปฏิทิน']]){
 test(`context copy supports ${language} and family-local time`,async({page})=>{
  await boot(page);await page.evaluate(language=>localStorage.setItem('famuhle-language',language),language);await page.reload();
  const tomorrow=page.getByTestId('today-tomorrow');await expect(tomorrow.getByRole('heading',{name:title,exact:true})).toBeVisible();await expect(tomorrow.getByRole('link',{name:label})).toBeVisible();await expect(tomorrow.getByRole('link',{name:/Zahnarzt morgen/})).toContainText('15:00');await page.getByRole('button',{name:'Customize',exact:true}).click();await expect(page.getByRole('region',{name:'Customize'}).getByRole('combobox',{name:`${title} · Size`})).toBeVisible();
 });
}

test('family-local midnight across DST changes the projected civil day without remounting',async({page})=>{
 await page.clock.install();await boot(page);const days=[];
 await page.route('**/api/actions/**',route=>route.fulfill({json:{results:[],scope:new URL(route.request().url()).searchParams.get('scope')}}));
 await page.route('**/api/events/**',route=>{const day=new URL(route.request().url()).searchParams.get('start');days.push(day);return route.fulfill({json:[event(day,`Tag ${day}`,null,null,'family-1',{date_start:day})]})});
 await page.evaluate(()=>{globalThis.__contextNow='2026-10-24T21:59:30Z';window.dispatchEvent(new Event('focus'))});
 const tomorrow=page.getByTestId('today-tomorrow');await expect(tomorrow).toContainText('Tag 2026-10-25');
 await page.evaluate(()=>{globalThis.__contextNow='2026-10-24T22:00:30Z'});await page.clock.fastForward(60_000);
 await expect(tomorrow).toContainText('Tag 2026-10-26');await expect(tomorrow).not.toContainText('Tag 2026-10-25');expect(days).toContain('2026-10-26');
});

test('source permission and session replacement remove cached private projection rows',async({page})=>{
 await boot(page);const tomorrow=page.getByTestId('today-tomorrow');const load=page.getByTestId('today-family-load');await expect(tomorrow).toContainText('Zahnarzt morgen');await expect(load).toContainText('Kinderarzt');
 await page.route('**/api/actions/**',route=>route.fulfill({json:{results:[],scope:new URL(route.request().url()).searchParams.get('scope')}}));await page.route('**/api/events/**',route=>route.fulfill({status:403,json:{detail:'Access revoked'}}));
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(tomorrow).not.toContainText('Zahnarzt morgen');await expect(load).not.toContainText('Kinderarzt');await expect(tomorrow).toContainText('teilweise');await expect(load).toContainText('teilweise');
 await page.route('**/api/events/**',route=>route.fulfill({json:[]}));await page.route('**/api/actions/**',route=>route.fulfill({json:{results:[action('replacement','Neuer Nutzer morgen','2026-10-11T08:00:00Z')],scope:'upcoming'}}));
 await page.evaluate(()=>window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:true}})));await expect(tomorrow).toContainText('Neuer Nutzer morgen');await expect(tomorrow).not.toContainText('Sporttasche packen');
});

test('same-day revalidation preserves layout while pending and removes denied source before other request finishes',async({page})=>{
 await boot(page);const tomorrow=page.getByTestId('today-tomorrow');const load=page.getByTestId('today-family-load');await expect(tomorrow).toContainText('Zahnarzt morgen');await expect(load).toContainText('Kinderarzt');
 const before=await tomorrow.boundingBox();
 let release;const pending=new Promise(resolve=>{release=resolve});let denied=false;
 await page.route('**/api/actions/**',async route=>{await pending;return route.fulfill({json:{results:[],scope:new URL(route.request().url()).searchParams.get('scope')}})});
 const calendarRoutes=[];await page.route('**/api/events/**',async route=>{calendarRoutes.push(route);await pending;if(!denied)return route.fulfill({json:[]})});
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect.poll(()=>calendarRoutes.length).toBe(2);
 await expect(tomorrow).toContainText('Zahnarzt morgen');await expect(load).toContainText('Kinderarzt');expect((await tomorrow.boundingBox()).height).toBe(before.height);
 denied=true;await Promise.all(calendarRoutes.map(route=>route.fulfill({status:403,json:{detail:'Access revoked'}})));
 await expect(tomorrow).not.toContainText('Zahnarzt morgen');await expect(load).not.toContainText('Kinderarzt');await expect(tomorrow).toContainText('teilweise');
 // The independently pending Action source remains visible until its own result.
 await expect(tomorrow).toContainText('Sporttasche packen');release();await expect(tomorrow).not.toContainText('Sporttasche packen');
});
