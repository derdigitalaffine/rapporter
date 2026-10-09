import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const secondFamily={id:'family-2',name:'Sehr lange Nebenfamilie mit langem Namen',slug:'nebenfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[]};

async function assertNoHorizontalOverflow(page){
  const metrics=await page.evaluate(()=>({
    viewport:window.innerWidth,
    html:document.documentElement.scrollWidth,
    body:document.body.scrollWidth,
    root:document.getElementById('root')?.scrollWidth||0,
  }));
  expect(metrics.html).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.body).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.root).toBeLessThanOrEqual(metrics.viewport);
}

test('narrow iPhone-sized viewport does not overflow and form controls stay at 16px',async({page})=>{
  await page.setViewportSize({width:320,height:568});
  await installApiMocks(page,{dismissOnboarding:true});

  await page.route('**/api/families/**',async route=>{
    const response=await route.fetch();
    const families=await response.json();
    return route.fulfill({response,body:JSON.stringify([...families,secondFamily])});
  });

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const familySelect=page.locator('.family-switcher select');
  await expect(familySelect).toBeVisible();
  await expect(familySelect).toHaveCSS('font-size','16px');
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button',{name:/Aufgaben|Tasks/}).click();
  await expect(page.locator('.smart-input input')).toBeVisible();
  await expect(page.locator('.smart-input input')).toHaveCSS('font-size','16px');
  await assertNoHorizontalOverflow(page);
});
