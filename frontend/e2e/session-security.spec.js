import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const now=new Date().toISOString();
const earlier=new Date(Date.now()-3600000).toISOString();

async function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

test('security center revokes sessions and gates revoke-all behind reauth',async({page})=>{
 await installApiMocks(page);
 let fresh=false;
 let sessions=[
  {id:'11111111-1111-4111-8111-111111111111',current:true,client:'Chrome · macOS',auth_method:'password',created_at:earlier,last_seen_at:now,last_reauthenticated_at:earlier,fresh_until:earlier,absolute_expires_at:now},
  {id:'22222222-2222-4222-8222-222222222222',current:false,client:'Safari · iPhone',auth_method:'password',created_at:earlier,last_seen_at:earlier,last_reauthenticated_at:earlier,fresh_until:earlier,absolute_expires_at:now},
  {id:'33333333-3333-4333-8333-333333333333',current:false,client:'Firefox · Linux',auth_method:'password',created_at:earlier,last_seen_at:earlier,last_reauthenticated_at:earlier,fresh_until:earlier,absolute_expires_at:now},
 ];
 await page.route('**/api/auth/sessions/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname;const method=request.method();
  if(path==='/api/auth/sessions/'&&method==='GET')return json(route,{sessions,fresh});
  if(path==='/api/auth/sessions/revoke-others/'&&method==='POST'){
   if(!fresh)return json(route,{detail:'Bitte bestätige deine Identität erneut.',code:'reauth_required'},403);
   sessions=sessions.filter(item=>item.current);return json(route,{revoked:2});
  }
  if(method==='DELETE'){
   const id=path.split('/').filter(Boolean).at(-1);sessions=sessions.filter(item=>item.id!==id);return route.fulfill({status:204,body:''});
  }
  return json(route,{});
 });
 await page.route('**/api/auth/reauth/password/',async route=>{fresh=true;return json(route,{reauthenticated:true,session:sessions[0]})});
 await page.goto('/?page=profile');await page.waitForLoadState('networkidle');
 const card=page.getByTestId('security-sessions');
 await expect(card.getByRole('heading',{name:'Aktive Sitzungen'})).toBeVisible();
 await expect(card.getByText('Chrome · macOS')).toBeVisible();
 await expect(card.getByText('Dieses Gerät')).toBeVisible();
 await expect(card.getByText('Safari · iPhone')).toBeVisible();

 const safariRow=card.locator('.security-session-row').filter({hasText:'Safari · iPhone'});
 await safariRow.getByRole('button',{name:'Abmelden'}).click();
 await expect(card.getByText('Safari · iPhone')).toHaveCount(0);

 await card.getByRole('button',{name:'Alle anderen abmelden'}).click();
 await expect(card.getByRole('heading',{name:'Identität bestätigen'})).toBeVisible();
 await card.getByLabel('Aktuelles Passwort').fill('correct-horse-battery-staple');
 await card.getByRole('button',{name:'Bestätigen'}).click();
 await expect(card.getByText('Firefox · Linux')).toHaveCount(0);
 await expect(card.getByText('Keine weiteren aktiven Sitzungen.')).toBeVisible();
});

test('revoking a second browser context makes its next auth request fail',async({browser,baseURL})=>{
 const contextA=await browser.newContext({baseURL});const contextB=await browser.newContext({baseURL});
 const pageA=await contextA.newPage();const pageB=await contextB.newPage();
 await installApiMocks(pageA);await installApiMocks(pageB);
 const sidA='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';const sidB='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';const revoked=new Set();
 const rows=()=>[
  {id:sidA,current:true,client:'Chrome · Desktop A',auth_method:'password',created_at:earlier,last_seen_at:now,last_reauthenticated_at:now,fresh_until:now,absolute_expires_at:now},
  {id:sidB,current:false,client:'Chrome · Desktop B',auth_method:'password',created_at:earlier,last_seen_at:now,last_reauthenticated_at:now,fresh_until:now,absolute_expires_at:now},
 ].filter(item=>!revoked.has(item.id));
 async function bindSessionRoutes(page,currentSid){
  await page.route('**/api/auth/session/',route=>revoked.has(currentSid)?json(route,{detail:'Sitzung abgelaufen.'},401):json(route,{authenticated:true,user:{id:1,username:'alex',email:'alex@example.test'},session:{id:currentSid}}));
  await page.route('**/api/auth/refresh/',route=>revoked.has(currentSid)?json(route,{detail:'Sitzung abgelaufen.'},401):json(route,{authenticated:true}));
 }
 await bindSessionRoutes(pageA,sidA);await bindSessionRoutes(pageB,sidB);
 await pageA.route('**/api/auth/sessions/**',async route=>{
  const request=route.request();const path=new URL(request.url()).pathname;
  if(path==='/api/auth/sessions/'&&request.method()==='GET')return json(route,{sessions:rows(),fresh:true});
  if(request.method()==='DELETE'){const sid=path.split('/').filter(Boolean).at(-1);revoked.add(sid);return route.fulfill({status:204,body:''})}
  return json(route,{});
 });
 try{
  await Promise.all([pageA.goto('/?page=profile'),pageB.goto('/')]);await Promise.all([pageA.waitForLoadState('networkidle'),pageB.waitForLoadState('networkidle')]);
  const card=pageA.getByTestId('security-sessions');await expect(card.getByText('Chrome · Desktop B')).toBeVisible();
  await card.locator('.security-session-row').filter({hasText:'Chrome · Desktop B'}).getByRole('button',{name:'Abmelden'}).click();
  await expect(card.getByText('Chrome · Desktop B')).toHaveCount(0);
  await pageB.reload();await pageB.waitForLoadState('networkidle');
  await expect(pageB.getByRole('heading',{name:'Anmelden'})).toBeVisible();
 }finally{await contextA.close();await contextB.close()}
});
