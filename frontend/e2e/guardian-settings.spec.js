import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const babyId='44444444-4444-4444-8444-444444444444';
const childMembershipId='33333333-3333-4333-8333-333333333333';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

test('guardian permissions stay separate from custody and require fresh auth',async({page})=>{
  await installApiMocks(page);
  let overview={
    family:'family-1',family_name:'Musterfamilie',actor_membership:'member-1',actor_role:'owner',
    children:[{
      baby:babyId,membership:childMembershipId,display_name:'Mia',
      guardians:[{membership:'member-1',display_name:'Alex',can_manage_account:true}],
      has_account_managing_guardian:true,can_manage_guardians:true,can_bootstrap_guardians:false,
    }],
  };
  let reauthPayload=null;
  let guardianPayload=null;
  const calls=[];

  await page.route('**/api/baby/guardian-settings/**',route=>json(route,overview));
  await page.route('**/api/auth/reauth/password/',route=>{reauthPayload=route.request().postDataJSON();calls.push('reauth');return json(route,{reauthenticated:true,session:{fresh:true}})});
  await page.route(`**/api/baby/profiles/${babyId}/guardians/`,route=>{
    guardianPayload=route.request().postDataJSON();calls.push('guardians');
    overview={...overview,children:overview.children.map(child=>({...child,guardians:[{membership:'member-1',display_name:'Alex',can_manage_account:true},{membership:'member-2',display_name:'Sam',can_manage_account:true}]}))};
    return json(route,{baby:babyId,membership:childMembershipId,display_name:'Mia',guardians:overview.children[0].guardians});
  });

  await page.goto('/?page=settings');
  await page.waitForLoadState('networkidle');
  const settings=page.locator('#children-permissions');
  await expect(settings.getByRole('heading',{name:'Kinder & Berechtigungen'})).toBeVisible();
  await expect(settings.getByText('Sorgeberechtigung beschreibt eure Beziehung. Guardian-Rechte steuern getrennt davon den Zugriff auf geschützte Kinderfunktionen.')).toBeVisible();
  await expect(settings.getByText('Guardians: Alex')).toBeVisible();

  await settings.getByRole('button',{name:/Verwalten/}).click();
  const dialog=page.getByRole('dialog',{name:'Mia'});
  await expect(dialog.getByText(/Sorgeberechtigung und Elternschaft werden separat gepflegt/)).toBeVisible();
  await dialog.getByText('Sam',{exact:true}).click();
  await dialog.getByLabel('Dein aktuelles Passwort').fill('correct-horse-battery-staple');
  await dialog.getByRole('button',{name:'Guardian-Rechte speichern'}).click();

  await expect(settings.getByText('Guardians: Alex, Sam')).toBeVisible();
  expect(calls).toEqual(['reauth','guardians']);
  expect(reauthPayload).toEqual({password:'correct-horse-battery-staple'});
  expect(guardianPayload).toEqual({guardians:[
    {membership:'member-1',can_manage_account:true},
    {membership:'member-2',can_manage_account:true},
  ]});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
