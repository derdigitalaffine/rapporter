import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const babyId='44444444-4444-4444-8444-444444444444';
const childMembershipId='33333333-3333-4333-8333-333333333333';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

test('child permissions show custody as automatic authority and legacy access separately',async({page})=>{
  await installApiMocks(page);
  const overview={
    family:'family-1',family_name:'Musterfamilie',actor_membership:'member-1',actor_role:'owner',
    children:[{
      baby:babyId,membership:childMembershipId,display_name:'Mia',custody_is_authority:true,
      guardians:[
        {membership:'member-1',display_name:'Alex',can_manage_account:true,source:'custody',has_custody:true},
        {membership:'member-2',display_name:'Sam',can_manage_account:true,source:'legacy_guardian',has_custody:false},
      ],
      has_account_managing_guardian:true,can_manage_guardians:true,can_bootstrap_guardians:false,
    }],
  };
  let guardianWrite=false;
  await page.route('**/api/baby/guardian-settings/**',route=>json(route,overview));
  await page.route(`**/api/baby/profiles/${babyId}/guardians/`,route=>{guardianWrite=true;return json(route,{detail:'unexpected'},500)});

  await page.goto('/?page=settings');
  await page.waitForLoadState('networkidle');
  const settings=page.locator('#children-permissions');
  await expect(settings.getByRole('heading',{name:'Kinder & Berechtigungen'})).toBeVisible();
  await expect(settings.getByText(/Gesetztes Sorgerecht gewährt automatisch/)).toBeVisible();
  await expect(settings.getByText('Sorgeberechtigt: Alex')).toBeVisible();
  await expect(settings.getByText(/Übergangszugriff \(Legacy Guardian\): Sam/)).toBeVisible();
  await expect(settings.getByRole('button',{name:/Verwalten/})).toHaveCount(0);
  expect(guardianWrite).toBe(false);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});