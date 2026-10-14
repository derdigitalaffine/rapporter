import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const fulfillJson=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
async function expectMinTarget(locator){const box=await locator.boundingBox();expect(box?.width||0).toBeGreaterThanOrEqual(44);expect(box?.height||0).toBeGreaterThanOrEqual(44)}
async function expectClasses(locator,...classes){const classList=await locator.evaluate(element=>[...element.classList]);expect(classList).toEqual(expect.arrayContaining(classes))}

test('email verification requires an explicit user click and scrubs token from browser state',async({page})=>{
 let verifyCalls=0;
 await page.route('**/api/auth/email/verify/',async route=>{
  verifyCalls+=1;
  expect(route.request().method()).toBe('POST');
  expect(route.request().postDataJSON()).toEqual({token:'signed-token'});
  expect(route.request().headers()['accept-language']).toBe('de');
  expect(route.request().headers().referer||'').not.toContain('signed-token');
  await fulfillJson(route,{verified:true,changed:true,kind:'primary'});
 });
 await page.goto('/verify-email/signed-token');
 await expect(page).toHaveURL(/\/verify-email\/$/);
 await expect(page.getByRole('heading',{name:'E-Mail-Adresse bestätigen'})).toBeVisible();
 expect(verifyCalls).toBe(0);
 await page.getByRole('button',{name:'E-Mail bestätigen'}).click();
 await expect(page.getByText('E-Mail-Adresse wurde bestätigt.')).toBeVisible();
 expect(verifyCalls).toBe(1);
});

test('invite registration has no username field and sends no username',async({page})=>{
 let registrationBody=null;
 await page.route('**/api/invite/token-identity/',route=>fulfillJson(route,{
  family:'family-1',family_name:'Musterfamilie',role:'adult',display_name:'Neu',email_hint:'',expires_at:new Date(Date.now()+86400000).toISOString(),active:true,
 }));
 await page.route('**/api/invite/token-identity/register/',async route=>{
  registrationBody=route.request().postDataJSON();
  await fulfillJson(route,{detail:'Test stoppt vor Navigation.'},409);
 });
 await page.goto('/invite/token-identity');
 await expect(page.getByRole('main').getByRole('heading',{name:'Musterfamilie'})).toBeVisible();
 await expect(page.getByLabel(/Benutzername/i)).toHaveCount(0);
 await page.getByLabel('Anzeigename').fill('Neue Person');
 await page.getByLabel('E-Mail').fill('new.member@example.test');
 await page.getByLabel('Passwort').fill('new-member-password');
 await page.getByRole('button',{name:'Konto erstellen & beitreten'}).click();
 await expect.poll(()=>registrationBody).not.toBeNull();
 expect(registrationBody).toMatchObject({email:'new.member@example.test',password:'new-member-password',display_name:'Neue Person'});
 expect(registrationBody).not.toHaveProperty('username');
});

test('profile shows verified email identity status',async({page})=>{
 await installApiMocks(page);
 await page.route('**/api/auth/email/identity/',route=>fulfillJson(route,{
  email:'alex@example.test',email_verified:true,email_verified_at:'2026-10-10T12:00:00Z',email_action_required:false,pending_email:'',pending_verification_sent_at:null,
 }));
 await page.goto('/?page=profile');
 await page.waitForLoadState('networkidle');
 const card=page.getByTestId('email-identity-card');
 await expect(card).toContainText('alex@example.test');
 await expect(card).toContainText('E-Mail bestätigt');
});

test('email identity actions keep explicit variants, payloads and touch targets',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await installApiMocks(page);
 const resends=[],changes=[];
 const identity={email:'alex@example.test',email_verified:false,email_verified_at:null,email_action_required:false,pending_email:'new@example.test',pending_verification_sent_at:'2026-10-11T12:00:00Z'};
 await page.route('**/api/auth/email/identity/',route=>fulfillJson(route,identity));
 await page.route('**/api/auth/email/verification/resend/',route=>{
  expect(route.request().method()).toBe('POST');
  resends.push(route.request().postDataJSON());
  return fulfillJson(route,{queued:true},202);
 });
 await page.route('**/api/auth/email/change/',route=>{
  expect(route.request().method()).toBe('POST');
  changes.push(route.request().postDataJSON());
  identity.pending_email=changes.at(-1).email;
  return fulfillJson(route,{queued:true},202);
 });
 await page.goto('/?page=profile');
 const card=page.getByTestId('email-identity-card');
 const noOverflow=async()=>expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 const directSecondary=card.locator(':scope > button.secondary.compact');
 await expect(directSecondary).toHaveCount(2);
 const primaryResend=directSecondary.filter({hasText:'Bestätigung erneut senden'});
 const edit=directSecondary.filter({hasText:'E-Mail-Adresse ändern'});
 const pendingResend=card.locator('.profile-privacy-note .text-button');

 await expect(primaryResend).toHaveAttribute('type','button');
 await expectClasses(primaryResend,'secondary','compact');
 await expectMinTarget(primaryResend);
 await noOverflow();
 await primaryResend.click();
 await expect.poll(()=>resends).toEqual([{target:'primary'}]);
 await expect(card).toContainText('new@example.test');
 await expect(pendingResend).toBeEnabled();
 await expect(pendingResend).toHaveAttribute('type','button');
 await expectClasses(pendingResend,'text-button');
 await expectMinTarget(pendingResend);
 await noOverflow();
 await pendingResend.click();
 await expect.poll(()=>resends).toEqual([{target:'primary'},{target:'pending'}]);
 await expect(edit).toBeVisible();
 await expect(edit).toHaveAttribute('type','button');
 await expectClasses(edit,'secondary','compact');
 await expectMinTarget(edit);

 await edit.click();
 const form=card.locator('form.profile-form');
 const email=form.locator('input[type=email]'),password=form.locator('input[type=password]');
 const cancel=form.locator('.dialog-actions .secondary');
 const submit=form.locator('.dialog-actions .primary');
 await expect(cancel).toHaveAttribute('type','button');
 await expectClasses(cancel,'secondary');
 await expectMinTarget(cancel);
 await expect(submit).toHaveAttribute('type','submit');
 await expectClasses(submit,'primary');
 await expectMinTarget(submit);
 await noOverflow();
 expect(changes).toEqual([]);
 await email.fill('canceled@example.test');
 await password.fill('current-password');
 await cancel.click();
 await expect(form).toHaveCount(0);
 expect(changes).toEqual([]);
 expect(resends).toEqual([{target:'primary'},{target:'pending'}]);
 await noOverflow();

 await edit.click();
 await expect(email).toHaveValue('');
 await expect(password).toHaveValue('');
 await email.fill('confirmed@example.test');
 await password.fill('current-password');
 await submit.focus();
 await page.keyboard.press('Enter');
 await expect.poll(()=>changes).toEqual([{email:'confirmed@example.test',password:'current-password'}]);
 await expect(form).toHaveCount(0);
 await expect(card).toContainText('confirmed@example.test');
 expect(resends).toEqual([{target:'primary'},{target:'pending'}]);
 await noOverflow();
});

test('legacy account path remains explicit for migration accounts',async({page})=>{
 await installApiMocks(page,{authenticated:false});
 const loginRequest=page.waitForRequest(request=>request.url().includes('/api/auth/login/')&&request.method()==='POST');
 await page.goto('/');
 await expect(page.getByLabel('E-Mail-Adresse')).toBeVisible();
 await expect(page.getByLabel('Benutzername')).toHaveCount(0);
 await page.getByRole('button',{name:'Bestandskonto / Superadmin'}).click();
 await expect(page.getByLabel('Benutzername')).toBeVisible();
 await page.getByLabel('Benutzername').fill('alex');
 await page.getByLabel('Passwort').fill('legacy-password');
 await page.getByRole('button',{name:'Anmelden',exact:true}).click();
 const request=await loginRequest;
 expect(request.postDataJSON()).toEqual({username:'alex',password:'legacy-password',legacy:true});
});
