import {expect} from '@playwright/test';

export async function expectActiveFamily(page,id){
 await expect.poll(()=>page.evaluate(()=>localStorage.getItem('famuhle-active-family'))).toBe(id);
}

export async function openFamilySwitcher(page){
 // Detail pages hide primary navigation. Use their visible back action before
 // opening More, including while an old-family request is still in flight.
 if(!await page.locator('.bottom-nav').isVisible()){
  await page.locator('main .page-head').getByRole('button',{name:/^(Zurück|Back)$/}).click();
 }
 if(!await page.locator('main[data-page="more"]').isVisible()){
  await page.locator('.bottom-nav').getByRole('button',{name:/^(Mehr|More)$/}).click();
 }
 const select=page.locator('main .family-switcher select');
 await expect(select).toBeVisible();
 return select;
}

export async function selectFamily(page,id){
 const select=await openFamilySwitcher(page);
 await select.selectOption(id);
 await expectActiveFamily(page,id);
 await expect(page.locator('main[data-page="home"]')).toBeVisible();
}
