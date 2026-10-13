import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page){
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await page.route('**/api/entitlements/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({tier:'family',display_name:'Family',capabilities:['messages','vehicles','loyalty','pregnancy_baby','pets','travel']})}));
  await page.goto('/');
  await page.waitForLoadState('networkidle');
}

test('global create message action resolves through registry into inbox composer once',async({page})=>{
  await boot(page);
  await page.locator('.global-create-fab').click();
  const palette=page.getByRole('dialog',{name:'Neu hinzufügen'});
  await expect(palette).toBeVisible();
  await palette.getByRole('button',{name:'Alle Aktionen'}).click();
  const message=palette.getByRole('button',{name:'Mitteilung',exact:true});
  await expect(message).toBeVisible();
  await message.click();
  await expect(page).toHaveURL(/page=inbox/);
  await expect(page).not.toHaveURL(/compose=1/);
  const composer=page.locator('#family-message-compose');
  await expect(composer).toBeVisible();
  await expect(composer.getByRole('textbox',{name:'Mitteilung'})).toBeFocused();
  await composer.getByRole('button',{name:'Abbrechen'}).click();
  await expect(composer).toHaveCount(0);
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#family-message-compose')).toHaveCount(0);
});
