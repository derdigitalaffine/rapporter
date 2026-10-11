import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const childMembershipId='33333333-3333-4333-8333-333333333333';
const babyId='44444444-4444-4444-8444-444444444444';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

async function bootGuardianChild(page){
  await installApiMocks(page);
  let identity={
    baby:babyId,
    membership:childMembershipId,
    user:3,
    display_name:'Mia',
    role:'child',
    access_state:'managed',
    email_hint:'',
    guardians:[{membership:'member-1',display_name:'Alex',can_manage_account:true}],
  };
  let reauthPayload=null;
  let activationPayload=null;
  const calls=[];
  await page.route('**/api/memberships/',route=>json(route,[
    {id:'member-1',family:'family-1',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''},
    {id:childMembershipId,family:'family-1',user:3,username:'child-mia',role:'child',display_name:'Mia',avatar:''},
  ]));
  await page.route(`**/api/baby/memberships/${childMembershipId}/identity/`,route=>json(route,identity));
  await page.route('**/api/auth/reauth/password/',route=>{
    reauthPayload=route.request().postDataJSON();
    calls.push('reauth');
    return json(route,{reauthenticated:true,session:{fresh:true}});
  });
  await page.route(`**/api/baby/profiles/${babyId}/activate-login/`,route=>{
    activationPayload=route.request().postDataJSON();
    calls.push('activate');
    identity={...identity,access_state:'verification_pending',email_hint:'m•••@example.test'};
    return json(route,identity,202);
  });
  await page.goto('/?page=members');
  await page.waitForLoadState('networkidle');
  return {getReauth:()=>reauthPayload,getActivation:()=>activationPayload,calls};
}

test('guardian activates the existing child identity with fresh auth',async({page})=>{
  const state=await bootGuardianChild(page);
  await page.locator('.member-profile-row').filter({hasText:'Mia'}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByText('Noch nicht aktiviert',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Eigenen Zugang einrichten'}).click();
  await dialog.getByLabel('E-Mail des Kindes').fill('mia@example.test');
  await dialog.getByLabel('Neues Passwort für das Kind').fill('correct-horse-battery-staple-child');
  await dialog.getByLabel('Neues Passwort wiederholen').fill('correct-horse-battery-staple-child');
  await dialog.getByLabel('Dein aktuelles Passwort').fill('correct-horse-battery-staple');
  await dialog.getByRole('button',{name:'Bestätigungs-E-Mail senden'}).click();

  await expect(dialog.getByText('Bestätigung offen',{exact:true})).toBeVisible();
  await expect(dialog.getByText(/m•••@example\.test/)).toBeVisible();
  expect(state.calls).toEqual(['reauth','activate']);
  expect(state.getReauth()).toEqual({password:'correct-horse-battery-staple'});
  expect(state.getActivation()).toEqual({email:'mia@example.test',password:'correct-horse-battery-staple-child'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
