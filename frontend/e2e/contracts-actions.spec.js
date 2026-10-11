import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
}

test('contracts hub keeps canonical action hierarchy and responsive targets',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  await page.goto('/?page=contracts');
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('heading',{name:'Verträge'})).toBeVisible();
  await expect(page.getByText('Noch keine Verträge')).toBeVisible();

  const back=page.getByRole('button',{name:'Zurück',exact:true});
  await expect(back).toHaveClass(/\bghost\b/);
  await expect(back).toHaveClass(/\bicon-button\b/);
  await expectMinTarget(back);

  const add=page.getByRole('button',{name:'Vertrag',exact:true});
  await expect(add).toHaveClass(/\bprimary\b/);
  await expect(add).toHaveClass(/\bcompact\b/);
  await expectMinTarget(add);

  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await page.setViewportSize({width:1440,height:900});
  await expect(back).toBeVisible();
  await expect(add).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
