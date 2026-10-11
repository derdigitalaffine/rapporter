import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const adminUser={id:99,username:'root',email:'root@example.test',email_verified:true,is_superadmin:true};
const session={id:'admin-session',current:true,client:'Mobile Safari',auth_method:'password',created_at:'2026-10-11T09:00:00Z',last_seen_at:'2026-10-11T10:00:00Z',last_reauthenticated_at:'2026-10-11T10:00:00Z',fresh_until:'2026-10-11T10:10:00Z',absolute_expires_at:'2027-01-01T00:00:00Z'};
const smtp={enabled:true,host:'smtp.example.test',port:587,username:'mailer',password_set:true,security:'starttls',timeout:10,from_email:'mail@example.test',reply_to:'reply@example.test',effective_source:'superadmin',configured:true};
const mailHealth={configured:true,counts:{queued:1,sending:0,retry:0,sent:12,failed:0,canceled:0},last_success_at:'2026-10-11T10:01:00Z',latency_seconds:{p50:1.2,p95:3.8},recent_error_classes:[]};
const userRow=(pendingEmail='',email='pat@example.test')=>({id:7,username:'user_pat',display_name:'Pat User',is_active:true,is_superuser:false,email,email_verified:true,email_managed:true,pending_email:pendingEmail,pending_verification_sent_at:pendingEmail?'2026-10-11T10:00:00Z':null,can_password_reset:true,memberships:[{id:'member-1',family_id:'family-1',family_name:'Familie Test',family_status:'active',role:'owner',display_name:'Pat User'}]});
const familyRow=()=>({id:'family-1',name:'Familie Test',slug:'familie-test',locale:'de',timezone:'Europe/Berlin',status:'active',member_count:3,owners:[{username:'user_pat',email:'pat@example.test',display_name:'Pat User'}],pending_owner_invites:[]});
const visibleNavButton=(page,label)=>page.locator('.superadmin-nav button:visible, .superadmin-mobile-nav button:visible').filter({hasText:new RegExp(`^${label}`)}).first();

async function installCockpitMocks(page,{loggedIn=true,onLogin,onLogout}={}){
 await installApiMocks(page);
 const state={loggedIn,pendingEmail:'',primaryEmail:'pat@example.test',families:[familyRow()]};
 await page.route('**/api/superadmin/auth/session/',route=>state.loggedIn?json(route,{authenticated:true,user:adminUser,session,fresh:true}):json(route,{detail:'Keine aktive Admin-Sitzung.'},401));
 await page.route('**/api/superadmin/auth/refresh/',route=>json(route,{detail:'Keine aktive Admin-Sitzung.'},401));
 await page.route('**/api/superadmin/auth/login/',route=>{const body=route.request().postDataJSON();onLogin?.(body);if(body.identifier==='root'&&body.password==='admin-password'){state.loggedIn=true;return json(route,{authenticated:true,user:adminUser,session})}return json(route,{detail:'Anmeldung fehlgeschlagen.'},401)});
 await page.route('**/api/superadmin/auth/logout/',route=>{state.loggedIn=false;onLogout?.();return json(route,{authenticated:false})});
 await page.route('**/api/superadmin/auth/sessions/',route=>json(route,{sessions:[session],fresh:true}));
 await page.route('**/api/superadmin/mail-health/',route=>json(route,mailHealth));
 await page.route('**/api/superadmin/mail-journal/**',route=>json(route,{count:1,limit:100,results:[{id:'mail-1',template_key:'password.reset',locale:'de',status:'sent',attempt_count:1,last_error_code:'',recipient_hint:'p***@e***.test',created_at:'2026-10-11T09:00:00Z',updated_at:'2026-10-11T09:00:02Z',sent_at:'2026-10-11T09:00:02Z',payload_cleared_at:'2026-10-11T09:00:02Z'}]}));
 await page.route('**/api/superadmin/users/**',route=>{const url=new URL(route.request().url());if(url.pathname==='/api/superadmin/users/'&&route.request().method()==='GET')return json(route,{count:1,limit:200,results:[userRow(state.pendingEmail,state.primaryEmail)]});return json(route,{detail:'not found'},404)});
 await page.route('**/api/superadmin/families/**',route=>{const url=new URL(route.request().url());if(url.pathname==='/api/superadmin/families/'&&route.request().method()==='GET')return json(route,state.families);return json(route,{detail:'not found'},404)});
 await page.route('**/api/superadmin/smtp/',route=>json(route,smtp));
 return state;
}

test('superadmin is a separately authenticated PWA with URL-stable cockpit navigation',async({page})=>{
 let loginBody=null;let loggedOut=false;
 await installCockpitMocks(page,{loggedIn:false,onLogin:body=>{loginBody=body},onLogout:()=>{loggedOut=true}});
 await page.goto('/superadmin/');
 await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href','/superadmin/manifest.webmanifest');
 await expect(page.getByRole('heading',{name:'Plattform sicher verwalten'})).toBeVisible();
 await expect(page.getByText('Diese PWA verwendet eine eigene Admin-Sitzung.')).toBeVisible();
 await page.getByLabel('E-Mail oder Admin-Benutzername').fill('root');
 await page.getByLabel('Passwort').fill('admin-password');
 await page.getByRole('button',{name:'Als Superadmin anmelden'}).click();
 await expect.poll(()=>loginBody).toEqual({identifier:'root',password:'admin-password'});
 await expect(page.getByRole('heading',{name:'Plattform im Blick'})).toBeVisible();
 await expect(visibleNavButton(page,'Nutzer')).toBeVisible();
 await visibleNavButton(page,'Nutzer').click();
 await expect(page).toHaveURL(/section=users/);
 await expect(page.getByRole('heading',{name:'Nutzer'})).toBeVisible();
 await expect(page.getByText('pat@example.test',{exact:true})).toBeVisible();
 await visibleNavButton(page,'Sicherheit').click();
 await expect(page).toHaveURL(/section=security/);
 await expect(page.getByText('Mobile Safari')).toBeVisible();
 await page.getByRole('button',{name:/Abmelden/}).click();
 await expect.poll(()=>loggedOut).toBe(true);
 await expect(page.getByRole('button',{name:'Als Superadmin anmelden'})).toBeVisible();
});

test('superadmin keeps tenant, direct recovery, SMTP and journal actions usable at 390px',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const state=await installCockpitMocks(page,{loggedIn:true});
 let reauthRequests=0;let savedSmtp=null;let saveAttempts=0;let resetRequests=0;let resetLinkRequests=0;let directEmailRequests=0;let createdFamily=null;
 await page.route('**/api/superadmin/auth/reauth/password/',route=>{reauthRequests+=1;expect(route.request().postDataJSON()).toEqual({password:'admin-password'});return json(route,{reauthenticated:true,session})});
 await page.unroute('**/api/superadmin/smtp/');
 await page.route('**/api/superadmin/smtp/',route=>{if(route.request().method()==='GET')return json(route,smtp);saveAttempts+=1;if(saveAttempts===1)return json(route,{detail:'fresh reauthentication required'},403);savedSmtp=route.request().postDataJSON();return json(route,{...smtp,...savedSmtp,password_set:true,password:undefined})});
 await page.unroute('**/api/superadmin/users/**');
 await page.route('**/api/superadmin/users/**',route=>{const url=new URL(route.request().url());const method=route.request().method();if(url.pathname==='/api/superadmin/users/'&&method==='GET')return json(route,{count:1,limit:200,results:[userRow(state.pendingEmail,state.primaryEmail)]});if(url.pathname==='/api/superadmin/users/7/email-change/'&&method==='POST'){state.pendingEmail=route.request().postDataJSON().email;return json(route,{queued:true,user:userRow(state.pendingEmail,state.primaryEmail)},202)}if(url.pathname==='/api/superadmin/users/7/email-direct/'&&method==='POST'){directEmailRequests+=1;state.primaryEmail=route.request().postDataJSON().email;state.pendingEmail='';return json(route,{updated:true,user:userRow('',state.primaryEmail)})}if(url.pathname==='/api/superadmin/users/7/password-reset-link/'&&method==='POST'){resetLinkRequests+=1;return json(route,{reset_url:'https://family.example.test/reset-password/uid/token-417'},201)}if(url.pathname==='/api/superadmin/users/7/password-reset/'&&method==='POST'){resetRequests+=1;return json(route,{queued:true},202)}return json(route,{detail:'not found'},404)});
 await page.unroute('**/api/superadmin/families/**');
 await page.route('**/api/superadmin/families/**',route=>{const url=new URL(route.request().url());const method=route.request().method();if(url.pathname==='/api/superadmin/families/'&&method==='GET')return json(route,state.families);if(url.pathname==='/api/superadmin/families/'&&method==='POST'){const body=route.request().postDataJSON();createdFamily={...familyRow(),id:'family-2',name:body.name,slug:'familie-zwei',member_count:0,owners:[],pending_owner_invites:[{id:'invite-1',email:body.owner_email,delivery_status:'preparing',last_sent_at:null}]};state.families=[...state.families,createdFamily];return json(route,{family:createdFamily,invite_id:'invite-1',delivery:'preparing'},201)}return json(route,{detail:'not found'},404)});

 await page.goto('/superadmin/?section=delivery');
 await expect(page.getByRole('heading',{name:'E-Mail & Zustellung'})).toBeVisible();
 const smtpPassword=page.locator('.superadmin-smtp input[type="password"]');
 await expect(smtpPassword).toHaveValue('');
 await expect(smtpPassword).toHaveAttribute('placeholder','Gespeichert · leer lassen zum Behalten');
 await page.getByLabel('SMTP-Host').fill('smtp.changed.test');
 await page.getByRole('button',{name:/SMTP speichern/}).click();
 await expect(page.getByRole('heading',{name:'Admin-Identität erneut bestätigen'})).toBeVisible();
 await page.getByLabel('Aktuelles Passwort').fill('admin-password');
 await page.getByRole('button',{name:'Bestätigen'}).click();
 await expect.poll(()=>savedSmtp?.host).toBe('smtp.changed.test');
 expect(savedSmtp.password).toBe('');expect(reauthRequests).toBe(1);
 await expect(page.locator('.superadmin-mail-journal')).toContainText('Passwort zurücksetzen');
 await expect(page.locator('.superadmin-mail-journal')).toContainText('p***@e***.test');

 await page.getByRole('button',{name:'Nutzer',exact:true}).click();
 const primaryEmailInput=page.getByLabel('Primäre E-Mail für Pat User');
 await primaryEmailInput.fill('pat.neu@example.test');
 await page.getByRole('button',{name:/Primäre E-Mail direkt setzen/}).click();
 await expect.poll(()=>directEmailRequests).toBe(1);
 await expect.poll(()=>state.primaryEmail).toBe('pat.neu@example.test');
 await expect(page.getByText('pat.neu@example.test',{exact:true})).toBeVisible();

 await page.getByRole('button',{name:'Reset-Link erzeugen'}).click();
 await expect.poll(()=>resetLinkRequests).toBe(1);
 const resetLinkField=page.getByLabel('Passwort-Reset-Link für Pat User');
 await expect(resetLinkField).toHaveValue('https://family.example.test/reset-password/uid/token-417');
 await expect(page.getByRole('button',{name:/Link kopieren/})).toBeVisible();

 await primaryEmailInput.fill('pat.verifiziert@example.test');
 await page.getByRole('button',{name:/Bestätigung an neue E-Mail senden/}).click();
 await expect.poll(()=>state.pendingEmail).toBe('pat.verifiziert@example.test');
 await expect(page.getByText(/Ausstehend: pat\.verifiziert@example\.test/)).toBeVisible();
 await page.getByRole('button',{name:'Reset-Mail senden'}).click();
 await expect.poll(()=>resetRequests).toBe(1);

 await page.getByRole('button',{name:'Familien',exact:true}).click();
 await page.getByLabel('Familienname').fill('Familie Zwei');
 await page.getByLabel('Owner-Name').fill('Alex');
 await page.getByLabel('Owner-E-Mail').fill('alex@example.test');
 await page.getByRole('button',{name:/Familie anlegen/}).click();
 await expect.poll(()=>createdFamily?.name).toBe('Familie Zwei');
 await expect(page.getByRole('heading',{name:'Familie Zwei'})).toBeVisible();

 await page.getByRole('button',{name:'Betrieb',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Betrieb & Health'})).toBeVisible();
 await expect(page.getByText('Keine Scheingenauigkeit')).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflow).toBeLessThanOrEqual(0);
});
