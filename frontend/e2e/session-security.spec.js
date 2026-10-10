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
