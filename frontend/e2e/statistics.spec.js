import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api';

const copies={de:{title:'Statistik',table:'Daten als Tabelle',filter:'Filter',member:'Mitglied',range:'7 Tage',sections:'Ansicht',routines:'Routinen'},en:{title:'Statistics',table:'Data as table',filter:'Filters',member:'Member',range:'7 days',sections:'View',routines:'Routines'},fr:{title:'Statistiques',table:'Données en tableau',filter:'Filtres',member:'Membre',range:'7 jours',sections:'Vue',routines:'Routines'},nl:{title:'Statistieken',table:'Gegevens als tabel',filter:'Filters',member:'Gezinslid',range:'7 dagen',sections:'Weergave',routines:'Routines'},th:{title:'สถิติ',table:'ข้อมูลแบบตาราง',filter:'ตัวกรอง',member:'สมาชิก',range:'7 วัน',sections:'มุมมอง',routines:'กิจวัตร'}};
function json(route,value,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)})}
function totals(completed=0,organized=0){return {completed,organized,reopened:1,effort_minutes:120,effort_coverage_count:8,task_completions:10,attributed:Math.max(0,completed-2),effort_coverage:80,actor_coverage:completed?90:null}}
function snapshot(family='family-1',role='owner'){
 const own=role==='child';const domains=[{key:'task',...totals(10,5)},{key:'routine',...totals(14,2)},{key:'shopping',...totals(18,9)}];
 return {meta:{family,from:'2026-09-15',to:'2026-10-14',timezone:'Europe/Berlin',generated_at:'2026-10-14T06:00:00Z',attribution_since:'2026-10-14T00:00:00Z',role,can_compare_members:['owner','adult'].includes(role),can_export:['owner','adult'].includes(role),scope:own?'self':'family',actor_coverage:90,effort_coverage:80,available_domains:['task','routine','shopping']},summary:{...totals(42,16),overdue_now:3},previous:totals(35,10),members:[{id:'member-1',name:family==='family-2'?'Pat':'Alex',self:true,...totals(20,8),domains:domains.map(d=>({...d,completed:Math.floor(d.completed/2)}))},...(['owner','adult'].includes(role)?[{id:'member-2',name:'Sam',self:false,...totals(20,8),domains:domains.map(d=>({...d,completed:Math.floor(d.completed/2)}))}]:[])],domains,timeseries:Array.from({length:30},(_,index)=>({date:new Date(Date.UTC(2026,8,15+index)).toISOString().slice(0,10),...totals(index%4+1,index%3)})),insights:[{key:'change',value:20,domain:null},{key:'coverage',value:90,domain:'task'},{key:'shopping_members',value:2,domain:'shopping'}]};
}
async function install(page,{language='de',role='owner',premium=true}={}){
 const state=await installApiMocks(page,{language});state.memberships[0].role=role;
 const stats={requests:[],detailFailure:false,overviewFailure:false,empty:false,delay:0,role};
 await page.route('**/api/entitlements/**',route=>json(route,{tier:premium?'vip':'light',display_name:premium?'VIP':'Light',capabilities:premium?['statistics','todo','shopping','calendar']:['todo','shopping','calendar']}));
 await page.route('**/api/statistics/**',async route=>{
  const url=new URL(route.request().url());stats.requests.push(url);
  if(stats.delay)await new Promise(resolve=>setTimeout(resolve,stats.delay));
  if(url.pathname==='/api/statistics/'){
   if(stats.overviewFailure)return route.abort('internetdisconnected');
   const value=snapshot(url.searchParams.get('family')||'family-1',role);
   if(stats.empty){value.summary=totals();value.domains=value.domains.map(d=>({...d,...totals()}));value.members=value.members.map(m=>({...m,...totals(),domains:m.domains.map(d=>({...d,...totals()}))}));value.timeseries=[];value.insights=[]}
   if(url.searchParams.get('member'))value.members=value.members.filter(m=>m.id===url.searchParams.get('member'));
   return json(route,value);
  }
  if(stats.detailFailure)return json(route,{detail:'Temporary failure'},503);
  const domain=url.pathname.includes('routines')?'routine':url.pathname.includes('shopping')?'shopping':'task';
  return json(route,{domain,count:stats.empty?0:2,page:1,page_size:50,has_next:false,active_routines:2,routines:domain==='routine'?[{id:'routine-1',name:'Pflanzen gießen',active:true,interval_days:7,completed:14,next_due:'2026-10-17T12:00:00Z',href:'?page=routines&family=family-1&routine=routine-1'}]:[],results:stats.empty?[]:[{id:'event-1',action:domain==='shopping'?'item_purchased':'completed',occurred_at:'2026-10-13T12:00:00Z',member:'member-1',effort_minutes:15,entity:domain==='routine'?'routine-1':'task-1',page:{task:'tasks',routine:'routines',shopping:'shopping'}[domain]},{id:'event-2',action:'created',occurred_at:'2026-10-12T12:00:00Z',member:null,effort_minutes:null,entity:'task-2',page:'tasks'}]});
 });
 return {state,stats};
}
async function open(page){await page.goto('/?page=statistics');await expect(page.locator('.statistics-kpis')).toBeVisible()}
async function view(page,value){if(await page.locator('.statistics-view-picker').isVisible())await page.locator('.statistics-view-picker select').selectOption(value);else await page.locator('.statistics-nav').getByRole('button',{name:copies.de[value]||({tasks:'Aufgaben',shopping:'Einkaufen',contributions:'Beiträge',overview:'Überblick'}[value]),exact:true}).click()}

test('statistics premium lock and guest have no statistics fetch',async({page})=>{
 const {stats}=await install(page,{premium:false});await page.goto('/?page=more');await page.getByRole('button',{name:'Statistik. Premium · gesperrt',exact:true}).click();await expect(page.getByText('Zur Zugriffsübersicht')).toBeVisible();expect(stats.requests).toHaveLength(0);
 await page.getByRole('button',{name:'Zur Zugriffsübersicht'}).click();await expect(page).toHaveURL(/page=more/);
});

test('statistics ranges, filters, history, reload and domain details',async({page})=>{
 const {stats}=await install(page);await open(page);
 for(const [label,key] of [['7 Tage','7d'],['30 Tage','30d'],['90 Tage','90d'],['1 Jahr','365d']]){await page.getByRole('button',{name:label,exact:true}).click();await expect.poll(()=>stats.requests.filter(u=>u.pathname==='/api/statistics/').at(-1)?.searchParams.get('range')).toBe(key)}
 await page.locator('.statistics-filter-details summary').click();await page.getByRole('combobox',{name:'Mitglied',exact:true}).selectOption('member-1');await expect.poll(()=>stats.requests.at(-1)?.searchParams.get('member')).toBe('member-1');
 await view(page,'routines');await expect(page.getByRole('link',{name:/Pflanzen gießen/})).toBeVisible();await expect(page.getByText(/Eine historische Fälligkeitsbasis/).first()).toBeVisible();await expect(page).toHaveURL(/stats_view=routines/);
 await page.reload();await expect(page.getByRole('link',{name:/Pflanzen gießen/})).toBeVisible();await page.goBack();await expect(page.locator('.statistics-distribution')).toBeVisible();
});

test('statistics custom range validation, effort coverage and adult CSV',async({page})=>{
 await install(page);await open(page);await page.getByRole('button',{name:'Eigener Zeitraum'}).click();await page.getByLabel('Von',{exact:true}).fill('2025-01-01');await page.getByLabel('Bis',{exact:true}).fill('2026-10-14');await page.getByRole('button',{name:'Anwenden',exact:true}).click();await expect(page.getByRole('alert')).toContainText('höchstens 365');
 await page.getByLabel('Von',{exact:true}).fill('2026-10-01');await page.getByRole('button',{name:'Anwenden',exact:true}).click();await expect(page).toHaveURL(/stats_from=2026-10-01/);
 await page.locator('.statistics-metric').getByRole('button',{name:'Geschätzter Aufwand'}).click();await expect(page.locator('.statistics-member').first()).toContainText('80 %');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Verlauf als CSV'}).click();expect((await download).suggestedFilename()).toContain('family-statistics-');
});

for(const role of ['teen','child','guest'])test(`statistics ${role} avoids named comparison and export`,async({page})=>{
 const {stats}=await install(page,{role});await page.goto('/?page=statistics');
 if(role==='guest'){await expect(page.getByText('Statistik ist für Gäste nicht verfügbar.')).toBeVisible();expect(stats.requests).toHaveLength(0);return}
 await expect(page.locator('.statistics-distribution')).toBeVisible();await expect(page.locator('.statistics-distribution')).not.toContainText('Sam');await expect(page.getByRole('button',{name:'Verlauf als CSV'})).toHaveCount(0);
 await expect(page.getByText(role==='child'?'Hier siehst du deinen eigenen Fortschritt. Jeder Beitrag zählt.':/Andere Mitglieder werden nicht persönlich verglichen/)).toBeVisible();
});

test('statistics partial detail failure and stale snapshot recover',async({page})=>{
 const {stats}=await install(page);await open(page);stats.detailFailure=true;await view(page,'routines');await expect(page.getByRole('alert')).toContainText('Detailbereich');await expect(page.locator('.statistics-domains')).toBeVisible();
 stats.detailFailure=false;await page.getByRole('button',{name:'Erneut versuchen'}).click();await expect(page.getByRole('link',{name:/Pflanzen gießen/})).toBeVisible();
 stats.overviewFailure=true;await page.getByRole('button',{name:'Aktualisieren',exact:true}).click();await expect(page.getByText(/Nicht aktuell · Stand/)).toBeVisible();await expect(page.locator('.statistics-domains')).toBeVisible();stats.overviewFailure=false;await page.getByRole('button',{name:'Erneut versuchen'}).click();await expect(page.getByText(/Nicht aktuell · Stand/)).toHaveCount(0);
});

test('statistics empty states show definitions without invented data',async({page})=>{
 const {stats}=await install(page);stats.empty=true;await open(page);await expect(page.getByRole('heading',{name:'Euer Verlauf beginnt hier'})).toBeVisible();await page.locator('.statistics-definitions summary').click();await expect(page.getByText(/Ältere Aufgaben ohne verlässlichen Akteur/)).toBeVisible();await view(page,'shopping');await expect(page.getByText('Keine Aktivitäten in diesem Zeitraum.')).toBeVisible();
});

for(const language of ['de','en','fr','nl','th'])test(`statistics ${language} responsive accessible charts and table`,async({page},testInfo)=>{
 await install(page,{language});await open(page);const copy=copies[language];await expect(page.locator('.statistics-header h1')).toHaveText(copy.title);
 for(const width of [320,390,1024,1440,1920]){await page.setViewportSize({width,height:900});await expect(page.locator('.statistics-kpis')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.screenshot({path:testInfo.outputPath(`statistics-${language}-${width}.png`),fullPage:true})}
 await page.setViewportSize({width:390,height:844});await page.locator('.statistics-distribution').getByRole('button',{name:copy.table}).focus();await page.keyboard.press('Enter');await expect(page.locator('.statistics-distribution table')).toBeVisible();await expect(page.locator('.statistics-distribution table')).toContainText('Alex');
 const axe=await new AxeBuilder({page}).include('.statistics-page').analyze();expect(axe.violations).toEqual([]);
 await page.setViewportSize({width:720,height:450});await page.locator('html').evaluate(el=>el.style.zoom='2');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.screenshot({path:testInfo.outputPath(`statistics-${language}-zoom.png`),fullPage:true});
});

test('statistics family switch discards pending previous-family requests',async({page})=>{
 const {state,stats}=await install(page);const second={...state.family,id:'family-2',name:'Zweite Familie',memberships:state.memberships.map(m=>({...m,family:'family-2'}))};await page.route('**/api/families/**',route=>json(route,[state.family,second]));
 stats.delay=250;await page.goto('/?page=statistics&family=family-1');await page.goto('/?page=statistics&family=family-2');await expect(page.locator('.statistics-header')).toContainText('Zweite Familie');await expect(page.locator('.statistics-distribution')).toContainText('Pat');await expect(page.locator('.statistics-distribution')).not.toContainText('Alex');expect(stats.requests.at(-1).searchParams.get('family')).toBe('family-2');
});
