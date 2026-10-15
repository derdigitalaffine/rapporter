import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function expectNoHorizontalOverflow(page){
  const sizes=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth}));
  expect(sizes.scrollWidth).toBeLessThanOrEqual(sizes.clientWidth);
}

async function openListEditor(page,width){
  await installApiMocks(page,{dismissOnboarding:true,language:'de'});
  await page.setViewportSize({width,height:844});
  await page.goto('/?page=shopping');
  await page.waitForLoadState('networkidle');
  const overflow=page.locator('.shopping-overflow');
  await overflow.locator('summary').click();
  await page.getByRole('button',{name:'Liste bearbeiten'}).click();
  return page.getByRole('dialog');
}

for(const width of [320,390]){
  test(`list editor uses the global sheet and form contract at ${width}px`,async({page})=>{
    const dialog=await openListEditor(page,width);
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveClass(/quick-sheet/);
    await expect(dialog.locator('form.form-shell')).toBeVisible();
    await expect(dialog.locator('form.quick-form')).toHaveCount(0);
    await expect(dialog.locator('.form-actions')).toBeVisible();
    await expect(dialog.getByRole('button',{name:'Abbrechen'})).toBeVisible();
    await expect(dialog.getByRole('button',{name:'Speichern'})).toBeVisible();
    await expect(dialog.getByLabel('Name')).toBeFocused();
    const box=await dialog.boundingBox();
    expect(box.width).toBeLessThanOrEqual(width);
    await expectNoHorizontalOverflow(page);
    await dialog.getByRole('button',{name:'Abbrechen'}).click();
    await expect(dialog).toHaveCount(0);
  });
}
