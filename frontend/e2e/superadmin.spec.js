import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

test('superadmin creates tenant, owner registers from emailed invite and lands only in that family',async({page,context})=>{
 await installApiMocks(page);page.on('dialog',dialog=>dialog.dismiss());let family=null;
 await page.route('**/api/auth/session/',route=>json(route,{authenticated:true,user:{id:99,username:'root',email:'root@example.test',is_superadmin:true}}));
 await page.route('**/api/superadmin/users/**',route=>json(route,{count:0,limit:200,offset:0,results:[]}));
 await page.route('**/api/superadmin/mail-journal/**',route=>json(route,{count:0,limit:100,results:[]}));
 await page.route('**/api/superadmin/families/**',async route=>{const url=new URL(route.request().url());const method=route.request().method();if(url.pathname==='/api/superadmin/families/'&&method==='GET')return json(route,family?[family]:[]);if(url.pathname==='/api/superadmin/families/'&&method==='POST'){const body=route.request().postDataJSON();family={id:'tenant-2',name:body.name,slug:'familie-zwei',locale:body.locale,timezone:body.timezone,status:'active',member_count:0,owners:[],memberships:[],pending_owner_invites:[{id:'owner-invite-id',email:body.owner_email,display_name:body.owner_name,expires_at:'2099-01-01T00:00:00Z',delivery_status:'preparing',last_sent_at:null}]};return json(route,{family,invite_id:'owner-invite-id',delivery:'preparing'},201)}return json(route,{detail:'not found'},404)});
 await page.goto('/');await expect(page.getByText('Superadmin',{exact:true})).toBeVisible();await page.getByLabel('Familienname').fill('Familie Zwei');await page.getByLabel('Owner-Name').fill('Pat');await page.getByLabel('Owner-E-Mail').fill('pat@example.test');await page.getByRole('button',{name:/Familie anlegen/}).click();await expect(page.getByRole('heading',{name:'Familie Zwei'})).toBeVisible();const pending=page.locator('.superadmin-pending');await expect(pending).toContainText('pat@example.test');await expect(pending).toContainText('Versand wird vorbereitet');

 const ownerPage=await context.newPage();let ownerRegistered=false;let registrationBody=null;
 await ownerPage.addInitScript(()=>{localStorage.setItem('famuhle-language','de');if(sessionStorage.getItem('owner-registered')==='1')localStorage.setItem('famuhle-session','1');else localStorage.removeItem('famuhle-session')});
 await ownerPage.route('**/api/invite/invite-owner/**',async route=>{const url=new URL(route.request().url());if(url.pathname==='/api/invite/invite-owner/'&&route.request().method()==='GET')return json(route,{family_id:'tenant-2',family_name:'Familie Zwei',role:'owner',email_hint:'pat@example.test',display_name:'Pat',expires_at:'2099-01-01T00:00:00Z',active:true});if(url.pathname==='/api/invite/invite-owner/register/'&&route.request().method()==='POST'){registrationBody=route.request().postDataJSON();ownerRegistered=true;family={...family,member_count:1,owners:[{username:'user_mockowner',email:'pat@example.test',display_name:'Pat'}],memberships:[{id:'membership-owner',family:'tenant-2',user:7,role:'owner',display_name:'Pat',username:'user_mockowner'}],pending_owner_invites:[]};await ownerPage.evaluate(()=>sessionStorage.setItem('owner-registered','1'));return json(route,{authenticated:true,email_verification_required:true,family,membership:family.memberships[0]},201)}return json(route,{detail:'not found'},404)});
 await ownerPage.route('**/api/auth/session/',route=>json(route,{authenticated:true,user:{id:7,username:'user_mockowner',email:'pat@example.test',is_superadmin:false}}));
 await ownerPage.route('**/api/auth/email/identity/',route=>json(route,{email:'pat@example.test',email_verified:false,email_verified_at:null,email_action_required:false,pending_email:'',pending_verification_sent_at:null}));
 await ownerPage.route('**/api/families/',route=>json(route,ownerRegistered?[family]:[]));
 await ownerPage.route('**/api/dashboard/**',route=>json(route,{tasks:[],task_lists:[],events:[],routines:[],shopping_lists:[],inbox_count:0,automation_count:0}));
 await ownerPage.route('**/api/profile/**',route=>json(route,{display_name:'Pat',username:'user_mockowner',role:'owner',avatar_url:'',birth_month:null,birth_day:null,birth_year:null,birthday_visibility:'day_month'}));
 await ownerPage.route('**/api/family-settings/**',route=>json(route,{family:'tenant-2',name:'Familie Zwei',slug:'familie-zwei',can_edit:true,image_url:'',address_street:'',address_house_number:'',address_postal_code:'',address_city:'',address_region:'',address_country_code:'',location_context:null}));
 await ownerPage.route('**/api/inbox/',route=>json(route,[]));await ownerPage.route('**/api/automation-rules/',route=>json(route,[]));
 await ownerPage.goto('/invite/invite-owner');await expect(ownerPage.getByText('Einladung zu FamilyOS')).toBeVisible();await expect(ownerPage.getByText('Inhaber',{exact:true})).toBeVisible();await expect(ownerPage.getByLabel('E-Mail')).toHaveValue('pat@example.test');await expect(ownerPage.getByLabel(/Benutzername/i)).toHaveCount(0);await ownerPage.getByLabel('Passwort').fill('owner-password-123');await ownerPage.getByRole('button',{name:'Konto erstellen & beitreten'}).click();
 await expect.poll(()=>registrationBody).not.toBeNull();expect(registrationBody).toMatchObject({email:'pat@example.test',password:'owner-password-123',display_name:'Pat'});expect(registrationBody).not.toHaveProperty('username');
 await expect(ownerPage).toHaveURL(/\?page=profile$/);const identityCard=ownerPage.getByTestId('email-identity-card');await expect(identityCard).toContainText('pat@example.test');await expect(identityCard).toContainText('E-Mail noch nicht bestätigt');await expect(ownerPage.getByText('Superadmin',{exact:true})).toHaveCount(0);await ownerPage.getByRole('button',{name:'Zurück'}).click();await expect(ownerPage.getByText('Familie Zwei · Europe/Berlin',{exact:true})).toBeVisible();
});

test('superadmin SMTP stays redacted, reauths save and test, and fits 390px',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await installApiMocks(page);
 let saved=null;let tested=null;let saveAttempts=0;let testAttempts=0;let reauthCount=0;
 const smtp={enabled:true,host:'smtp.example.test',port:587,username:'mailer',password_set:true,security:'starttls',timeout:10,from_email:'mail@example.test',reply_to:'reply@example.test',effective_source:'superadmin',configured:true};
 await page.route('**/api/auth/session/',route=>json(route,{authenticated:true,user:{id:99,username:'root',email:'root@example.test',is_superadmin:true}}));
 await page.route('**/api/superadmin/families/',route=>json(route,[]));
 await page.route('**/api/superadmin/users/**',route=>json(route,{count:0,limit:200,offset:0,results:[]}));
 await page.route('**/api/superadmin/mail-journal/**',route=>json(route,{count:0,limit:100,results:[]}));
 await page.route('**/api/superadmin/smtp/',async route=>{
  const method=route.request().method();
  if(method==='GET')return json(route,smtp);
  if(method==='PUT'){
   saveAttempts+=1;
   if(saveAttempts===1)return json(route,{detail:'fresh reauthentication required'},403);
   saved=route.request().postDataJSON();
   return json(route,{...smtp,...saved,password_set:true,password:undefined});
  }
  return json(route,{detail:'not found'},404);
 });
 await page.route('**/api/superadmin/smtp/test/',async route=>{
  testAttempts+=1;
  if(testAttempts===1)return json(route,{detail:'fresh reauthentication required'},403);
  tested=route.request().postDataJSON();return json(route,{ok:true,accepted:true,source:'superadmin'});
 });
 await page.route('**/api/auth/reauth/password/',async route=>{reauthCount+=1;expect(route.request().postDataJSON()).toEqual({password:'admin-password'});return json(route,{ok:true})});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Transaktionsmail'})).toBeVisible();
 const password=page.locator('.superadmin-smtp input[type="password"]');
 await expect(password).toHaveValue('');
 await expect(password).toHaveAttribute('placeholder','Gespeichert · leer lassen zum Behalten');
 await page.getByLabel('SMTP-Host').fill('smtp.changed.test');
 await page.getByRole('button',{name:/SMTP speichern/}).click();
 await expect(page.getByRole('heading',{name:'Identität erneut bestätigen'})).toBeVisible();
 await page.getByLabel('Aktuelles Passwort').fill('admin-password');
 await page.getByRole('button',{name:'Bestätigen'}).click();
 await expect.poll(()=>saved).not.toBeNull();
 expect(saved.host).toBe('smtp.changed.test');expect(saved.password).toBe('');
 await expect(password).toHaveValue('');
 await page.getByLabel('Testadresse').fill('target@example.test');
 await page.getByRole('button',{name:'Testmail senden'}).click();
 await expect(page.getByRole('heading',{name:'Identität erneut bestätigen'})).toBeVisible();
 await page.getByLabel('Aktuelles Passwort').fill('admin-password');
 await page.getByRole('button',{name:'Bestätigen'}).click();
 await expect.poll(()=>tested).not.toBeNull();expect(tested).toEqual({recipient:'target@example.test'});expect(reauthCount).toBe(2);
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflow).toBeLessThanOrEqual(0);
});

test('superadmin can request verified email change, send password reset and inspect redacted mail journal',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await installApiMocks(page);
 let pendingEmail='';let emailAttempts=0;let resetRequests=0;let reauthRequests=0;
 const smtp={enabled:false,host:'',port:587,username:'',password_set:false,security:'starttls',timeout:10,from_email:'',reply_to:'',effective_source:'environment',configured:false};
 const userRow=()=>({id:7,username:'user_pat',display_name:'Pat User',is_active:true,is_superuser:false,email:'pat@example.test',email_verified:true,email_managed:true,pending_email:pendingEmail,pending_verification_sent_at:pendingEmail?'2026-10-11T10:00:00Z':null,can_password_reset:true,memberships:[{id:'member-1',family_id:'family-1',family_name:'Familie Test',family_status:'active',role:'owner',display_name:'Pat User'}]});
 await page.route('**/api/auth/session/',route=>json(route,{authenticated:true,user:{id:99,username:'root',email:'root@example.test',is_superadmin:true}}));
 await page.route('**/api/superadmin/families/',route=>json(route,[]));
 await page.route('**/api/superadmin/smtp/',route=>json(route,smtp));
 await page.route('**/api/superadmin/mail-journal/**',route=>json(route,{count:1,limit:100,results:[{id:'mail-1',template_key:'password.reset',locale:'de',status:'sent',attempt_count:1,last_error_code:'',recipient_hint:'h***@p***.test',created_at:'2026-10-11T09:00:00Z',updated_at:'2026-10-11T09:00:02Z',sent_at:'2026-10-11T09:00:02Z',payload_cleared_at:'2026-10-11T09:00:02Z'}]}));
 await page.route('**/api/superadmin/users/**',async route=>{
  const url=new URL(route.request().url());const method=route.request().method();
  if(url.pathname==='/api/superadmin/users/'&&method==='GET')return json(route,{count:1,limit:200,offset:0,results:[userRow()]});
  if(url.pathname==='/api/superadmin/users/7/email-change/'&&method==='POST'){
   emailAttempts+=1;if(emailAttempts===1)return json(route,{detail:'fresh reauthentication required'},403);
   pendingEmail=route.request().postDataJSON().email;return json(route,{queued:true,user:userRow()},202);
  }
  if(url.pathname==='/api/superadmin/users/7/password-reset/'&&method==='POST'){resetRequests+=1;return json(route,{queued:true},202)}
  return json(route,{detail:'not found'},404);
 });
 await page.route('**/api/auth/reauth/password/',route=>{reauthRequests+=1;expect(route.request().postDataJSON()).toEqual({password:'admin-password'});return json(route,{ok:true})});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Nutzerkonten'})).toBeVisible();
 await expect(page.getByText('pat@example.test',{exact:true})).toBeVisible();
 await page.getByLabel('Neue E-Mail für Pat User').fill('pat.neu@example.test');
 await page.getByRole('button',{name:'E-Mail-Änderung starten'}).click();
 await expect(page.getByRole('heading',{name:'Identität erneut bestätigen'})).toBeVisible();
 await page.getByLabel('Aktuelles Passwort').fill('admin-password');
 await page.getByRole('button',{name:'Bestätigen'}).click();
 await expect.poll(()=>pendingEmail).toBe('pat.neu@example.test');
 await expect(page.getByText(/Ausstehend: pat\.neu@example\.test/)).toBeVisible();
 await page.getByRole('button',{name:'Passwort-Reset senden'}).click();
 await expect.poll(()=>resetRequests).toBe(1);
 expect(reauthRequests).toBe(1);
 const journal=page.locator('.superadmin-mail-journal');
 await expect(journal).toContainText('Passwort zurücksetzen');
 await expect(journal).toContainText('Versendet');
 await expect(journal).toContainText('h***@p***.test');
 await expect(page.getByText('hidden.recipient@private.test',{exact:true})).toHaveCount(0);
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflow).toBeLessThanOrEqual(0);
});
