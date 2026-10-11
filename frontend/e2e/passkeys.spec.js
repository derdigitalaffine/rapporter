import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const challenge='AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8';
const now=new Date().toISOString();
function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

async function installVirtualAuthenticator(page){
 const client=await page.context().newCDPSession(page);
 await client.send('WebAuthn.enable');
 const {authenticatorId}=await client.send('WebAuthn.addVirtualAuthenticator',{options:{protocol:'ctap2',transport:'internal',hasResidentKey:true,hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
 return async()=>{await client.send('WebAuthn.removeVirtualAuthenticator',{authenticatorId}).catch(()=>{});await client.detach().catch(()=>{})};
}

test('password session can add a passkey and then sign in passwordless',async({page})=>{
 await installApiMocks(page);
 const cleanup=await installVirtualAuthenticator(page);
 let rows=[];let registeredCredential=null;
 await page.route('**/api/auth/passkeys/**',async route=>{
  const request=route.request();const path=new URL(request.url()).pathname;const method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  if(path==='/api/auth/passkeys/'&&method==='GET')return json(route,{results:rows});
  if(path==='/api/auth/passkeys/registration/options/'&&method==='POST')return json(route,{challenge_id:'register-1',options:{challenge,rp:{id:'127.0.0.1',name:'FamilyOS'},user:{id:'dXNlci0x',name:'alex@example.test',displayName:'Alex'},pubKeyCredParams:[{type:'public-key',alg:-7},{type:'public-key',alg:-257}],timeout:60000,attestation:'none',authenticatorSelection:{residentKey:'required',userVerification:'required'},excludeCredentials:[]}});
  if(path==='/api/auth/passkeys/registration/verify/'&&method==='POST'){
   registeredCredential=body.credential;
   rows=[{id:'11111111-1111-4111-8111-111111111111',name:body.name,transports:registeredCredential?.response?.transports||[],device_type:'multi_device',backed_up:true,created_at:now,last_used_at:null}];
   return json(route,rows[0],201);
  }
  if(path==='/api/auth/passkeys/authentication/options/'&&method==='POST')return json(route,{challenge_id:'login-1',options:{challenge,rpId:'127.0.0.1',timeout:60000,userVerification:'required'}});
  if(path==='/api/auth/passkeys/authentication/verify/'&&method==='POST'){
   expect(body.challenge_id).toBe('login-1');expect(body.credential?.id).toBeTruthy();expect(body.credential?.response?.signature).toBeTruthy();
   return json(route,{authenticated:true,email_verified:true,email_action_required:false,session:{id:'passkey-session'}});
  }
  return json(route,{});
 });
 try{
  await page.goto('/?page=profile');await page.waitForLoadState('networkidle');
  const card=page.getByTestId('passkey-security');
  await expect(card.getByRole('heading',{name:'Passkeys'})).toBeVisible();
  await card.getByLabel('Name des Passkeys').fill('Test-Laptop');
  await card.getByRole('button',{name:'Passkey hinzufügen'}).click();
  await expect(card.getByText('Test-Laptop')).toBeVisible();
  expect(registeredCredential?.response?.attestationObject).toBeTruthy();

  await page.evaluate(()=>{localStorage.removeItem('famuhle-session');window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:false}}))});
  await expect(page.getByRole('heading',{name:'Anmelden'})).toBeVisible();
  await page.getByRole('button',{name:'Mit Passkey anmelden'}).click();
  await expect(page.getByRole('heading',{name:'Anmelden'})).toHaveCount(0);
  await expect.poll(()=>page.evaluate(()=>localStorage.getItem('famuhle-session'))).toBe('1');
 }finally{await cleanup()}
});
