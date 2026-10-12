import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const metric=(value,previous=0)=>({value,previous,delta:value===null?null:value-previous,change_pct:previous?100*(value-previous)/previous:null});
const period={key:'30d',timezone:'UTC',start:'2026-09-12T00:00:00Z',end:'2026-10-12T00:00:00Z',comparison_start:'2026-08-13T00:00:00Z'};
const row=id=>({id,username:`user_${id}`,display_name:`Person ${id}`,email:`p${id}@example.test`,is_active:true,is_superuser:false,email_verified:true,family_count:2,can_password_reset:true,memberships:[]});
const overview={period,totals:{families:{total:500,active:490,suspended:10},users:1234,verified_email_users:1200},activity:{active_users:metric(90,80),active_families:metric(50,40),new_users:metric(10),new_families:metric(5)},timeseries:[{day:'2026-10-11',active_users:12,active_families:7}],definitions:{active_user:'Meaningful activity in the selected period.',active_family:'Family with a meaningful active user.'},onboarding:{invites:{created:metric(10),sent:metric(8),accepted:metric(6),email_failed:metric(1),expired:metric(2),revoked:metric(0),send_to_accept_rate_pct:metric(75),median_seconds_to_accept:metric(120)},owner_invites:{created:metric(2)},activation:{definition_version:'membership-v1',accepted_memberships:metric(6),email_verified:metric(5),meaningful_activity_within_7d:metric(4),activated:metric(4),activation_rate_pct:metric(66.7)},measurement:{}},retention:{users:{d7:{eligible:metric(3),retained:metric(1),rate_pct:metric(null),small_cohort_suppressed:true}},families:{d90:{eligible:metric(0),retained:metric(0),rate_pct:metric(null),small_cohort_suppressed:false}},measurement:{usage_retention_days:60,observation_cutoff:'2026-08-13T00:00:00Z'}}};
const nav=(page,text)=>page.locator('.superadmin-nav button:visible, .superadmin-mobile-nav button:visible').filter({hasText:new RegExp(`^${text}`)}).first();
async function mocks(page){
 await installApiMocks(page);const requests=[],state={securityFails:true,detailFails:true};
 await page.route('**/api/superadmin/**',async route=>{
  const url=new URL(route.request().url()),p=url.pathname.slice('/api/superadmin'.length);requests.push({path:p,query:url.searchParams.toString()});
  if(p==='/auth/session/')return json(route,{authenticated:true,user:{id:99,username:'root',is_superadmin:true},session:{id:'s'}});
  if(p==='/auth/sessions/')return json(route,{sessions:[],fresh:true});
  if(p==='/smtp/')return json(route,{configured:true,enabled:true,password_set:true});
  if(p==='/mail-health/')return json(route,{configured:true,counts:{},latency_seconds:{},recent_error_classes:[]});
  if(p==='/mail-journal/')return json(route,{count:0,results:[]});
  if(p==='/analytics/overview/')return json(route,{...overview,period:{...period,key:url.searchParams.get('period'),...(url.searchParams.get('period')==='90d'?{start:'2026-07-14T00:00:00Z',comparison_start:'2026-04-15T00:00:00Z'}:{})}});
  if(p==='/security/summary/')return state.securityFails?json(route,{},503):json(route,{period,authentication:{login_success:metric(12),login_failure:metric(2),login_success_rate_pct:85.7,passkey_share_pct:null},security_events:{rate_limited:metric(0)},definitions:{}});
  if(p==='/delivery/summary/')return json(route,{period,mail:{smtp_configured:true,sent:metric(8),failed:metric(2),success_rate_pct:80,failure_classes:[{error_class:'smtp_timeout',count:2}]},push:{sent:metric(0),failed:metric(0),success_rate_pct:null,subscriptions:{active:0},failure_classes:[]}});
  if(p==='/operations/health/')return json(route,{checked_at:period.end,status:'unknown',components:{database:{status:'healthy',reason:'database_query_ok'},workers:{mail_worker:{status:'unknown',reason:'no_canonical_heartbeat_source'}}}});
  if(p==='/users/') {const offset=Number(url.searchParams.get('offset'));return json(route,{count:60,limit:25,offset,results:Array.from({length:25},(_,i)=>row(offset+i+1))})}
  if(p==='/users/1/')return state.detailFails?json(route,{},503):json(route,{user:row(1),security:{sessions:{active:3},passkeys:{active:2},last_successful_login_at:period.end},auth_timeline:{results:[]},invitations:{results:[]}});
  if(p==='/families/')return json(route,{count:1,results:[{id:'family-1',name:'Family One',slug:'family-one',locale:'en',timezone:'UTC',status:'active',owners:[],member_count:2}]});
  if(p==='/families/family-1/')return json(route,{family:{id:'family-1',name:'Family One'},activity:{active_users_7d:2,active_users_30d:4},memberships:[],superadmin_audit:{results:[]}});
  if(p==='/audit/'){if(url.searchParams.get('export')==='csv')return route.fulfill({contentType:'text/csv',headers:{'Content-Disposition':'attachment; filename="audit.csv"'},body:'event_key,outcome\nauth.login.failed,failed\n'});return json(route,{period,pagination:{count:26,limit:25,offset:0,next_offset:25},results:[{id:1,occurred_at:period.end,event_key:'auth.login.failed',actor_class:'user',actor_id:1,target_type:'user',outcome:'failed',request_id:'safe-correlation'}]})}
  return json(route,{},404);
 });return {requests,state};
}
test('internal totals and server directories are independent, with canonical details and recoverable partial failures',async({page})=>{
 const {requests,state}=await mocks(page);await page.goto('/superadmin/');
 const insight=page.getByTestId('admin-internal-overview');await expect(insight.locator('dd').filter({hasText:/^1[.,]?234$/})).toBeVisible();
 await page.getByLabel('Zeitraum',{exact:true}).selectOption('90d');await expect(insight.getByText(/Eingeschränkte Beobachtungsabdeckung/)).toBeVisible();
 await page.getByLabel('Zeitraum',{exact:true}).selectOption('7d');await expect(page).toHaveURL(/period=7d/);await expect.poll(()=>requests.some(r=>r.path==='/analytics/overview/'&&r.query==='period=7d')).toBe(true);
 await nav(page,'Nutzer').click();await expect(page.getByRole('button',{name:'Primäre E-Mail direkt setzen'}).first()).toBeVisible();
 await expect.poll(()=>requests.some(r=>r.path==='/users/'&&r.query.includes('limit=25'))).toBe(true);expect(requests.some(r=>r.query.includes('limit=200'))).toBe(false);
 await page.getByLabel('Nutzer suchen',{exact:true}).fill('pat@example.test');await expect.poll(()=>requests.some(r=>r.path==='/users/'&&new URLSearchParams(r.query).get('q')==='pat@example.test')).toBe(true);expect(page.url()).not.toContain('pat');
 await page.getByLabel('Status',{exact:true}).selectOption('inactive');await page.getByLabel('Sortierung',{exact:true}).selectOption('-last_activity');await page.getByRole('button',{name:'Weiter',exact:true}).click();await expect.poll(()=>requests.some(r=>r.path==='/users/'&&new URLSearchParams(r.query).get('offset')==='25'&&r.query.includes('status=inactive')&&r.query.includes('sort=-last_activity'))).toBe(true);
 await page.getByRole('link',{name:'Nutzer verwalten',exact:true}).click();await expect(page).toHaveURL(/mode=crud/);await expect(page).toHaveURL(/period=7d/);await expect(page.locator('.superadmin-top')).toHaveCount(1);await expect(page.locator('.user-crud-top')).toHaveCount(0);await expect(page.getByRole('main')).toHaveCount(1);await expect(page.getByRole('main')).toBeVisible();
 await page.getByRole('button',{name:'Details',exact:true}).first().click();await expect(page.getByRole('region',{name:'Nutzerdetails'})).toBeVisible();await expect(page.getByRole('region',{name:'Nutzerdetails'}).getByRole('alert')).toBeVisible();state.detailFails=false;await page.getByRole('region',{name:'Nutzerdetails'}).getByRole('button',{name:'Erneut laden'}).click();await expect(page.getByRole('region',{name:'Nutzerdetails'}).getByText('Person 1',{exact:true})).toBeVisible();
 await nav(page,'Sicherheit').click();await expect(page.getByTestId('admin-security-insights').getByRole('alert')).toBeVisible();await expect(page.getByRole('heading',{name:'Admin-Sicherheit'})).toBeVisible();state.securityFails=false;await page.getByTestId('admin-security-insights').getByRole('button',{name:'Erneut laden'}).click();await expect(page.getByTestId('admin-security-insights').getByText('85,7 %',{exact:true})).toBeVisible();
});
test('onboarding, delivery, health and filtered audited export use authoritative semantics',async({page})=>{
 const {requests}=await mocks(page);await page.goto('/superadmin/?section=onboarding');await expect(page.getByTestId('admin-onboarding').getByText('membership-v1',{exact:false})).toBeVisible();await expect(page.getByTestId('admin-onboarding').getByText(/n < 5/)).toBeVisible();await expect(page.getByTestId('admin-onboarding').getByText('120 s',{exact:true})).toBeVisible();
 await nav(page,'Familien').click();await page.getByRole('button',{name:'Details',exact:true}).click();const family=page.getByRole('region',{name:'Familiendetails'});await expect(family.getByText('Aktive Nutzer · 7 Tage',{exact:true})).toBeVisible();await expect(family.getByText('Aktive Nutzer · 30 Tage',{exact:true})).toBeVisible();
 await nav(page,'E-Mail').click();await expect(page.getByTestId('admin-delivery-insights').getByText('smtp_timeout: 2')).toBeVisible();await expect(page.getByTestId('admin-delivery-insights').getByText(/keine Lese- oder Inbox-Bestätigung/)).toBeVisible();
 await nav(page,'Betrieb').click();await expect(page.getByTestId('admin-operations-insights').getByText('Keine verlässliche Heartbeat-Quelle')).toBeVisible();await expect(page.getByTestId('admin-operations-insights')).not.toContainText('no_canonical_heartbeat_source');
 await nav(page,'Audit').click();await page.getByLabel('Ergebnis',{exact:true}).selectOption('failed');await page.getByLabel('Akteur',{exact:true}).selectOption('user');await page.getByRole('button',{name:'Filter anwenden'}).click();await expect.poll(()=>requests.some(r=>r.path==='/audit/'&&r.query.includes('outcome=failed')&&r.query.includes('actor_class=user'))).toBe(true);await expect(page).toHaveURL(/audit_outcome=failed/);
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Gefiltertes CSV exportieren'}).click();await download;const exported=requests.find(r=>r.path==='/audit/'&&r.query.includes('export=csv'));expect(exported.query).toContain('outcome=failed');expect(exported.query).not.toContain('limit=');expect(exported.query).not.toContain('offset=');
});
test('new cockpit surfaces support all five locales, keyboard navigation and narrow/zoom layouts',async({page})=>{
 await mocks(page);await page.goto('/superadmin/?section=operations');
 for(const [language,label,reason] of [['de','Systemzustand','Keine verlässliche Heartbeat-Quelle'],['en','System health','No authoritative heartbeat source'],['fr','État du système','Aucune source fiable de signal de présence'],['nl','Systeemstatus','Geen gezaghebbende heartbeatbron'],['th','สถานะระบบ','ไม่มีแหล่งสัญญาณสถานะที่เชื่อถือได้']]){
  await page.locator('.admin-cockpit-toolbar select').nth(1).selectOption(language);await expect(page.getByTestId('admin-operations-insights').getByRole('heading',{name:label,exact:true})).toBeVisible();await expect(page.getByTestId('admin-operations-insights').getByText(reason,{exact:true})).toBeVisible();await expect(page.getByTestId('admin-operations-insights')).not.toContainText('adminCockpit.');
 }
 await page.locator('.admin-cockpit-toolbar select').nth(1).selectOption('de');
 for(const width of [320,390,1024,1440]){await page.setViewportSize({width,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)}
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.style.zoom='2');await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.evaluate(()=>document.documentElement.style.zoom='1');
 const audit=nav(page,'Audit');await audit.focus();await page.keyboard.press('Enter');await expect(page).toHaveURL(/section=audit/);const button=page.getByRole('button',{name:'Filter anwenden'});expect((await button.boundingBox()).height).toBeGreaterThanOrEqual(44);
});
test('a normal family session never grants access to the separately authenticated admin cockpit',async({page})=>{
 await installApiMocks(page);await page.route('**/api/superadmin/auth/session/',route=>json(route,{},401));await page.route('**/api/superadmin/auth/refresh/',route=>json(route,{},401));await page.goto('/superadmin/?section=audit');await expect(page.getByRole('button',{name:'Als Superadmin anmelden'})).toBeVisible();await expect(page.getByTestId('admin-audit')).toHaveCount(0);
});
test('ID lookup honors canonical status and changed filters discard the old detail',async({page})=>{
 const {state}=await mocks(page);state.detailFails=false;
 await page.route('**/api/superadmin/users/?**',route=>json(route,{count:0,results:[]}));
 await page.goto('/superadmin/?section=users');await page.getByLabel('Status',{exact:true}).selectOption('inactive');await page.getByLabel('Nutzer suchen',{exact:true}).fill('1');
 await expect(page.getByText('Keine Nutzerkonten gefunden',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Person 1',exact:true})).toHaveCount(0);
 await page.getByLabel('Status',{exact:true}).selectOption('active');await expect(page.getByRole('heading',{name:'Person 1',exact:true})).toBeVisible();await page.getByRole('button',{name:'Details',exact:true}).click();await expect(page.getByRole('region',{name:'Nutzerdetails'})).toBeVisible();await page.getByLabel('Status',{exact:true}).selectOption('inactive');await expect(page.getByRole('region',{name:'Nutzerdetails'})).toHaveCount(0);
});
