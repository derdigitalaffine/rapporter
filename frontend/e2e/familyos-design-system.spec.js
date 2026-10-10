import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,path='/'){
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.app-shell')).toBeVisible();
}

async function expectNoOverflow(page){
  const metrics=await page.evaluate(()=>({viewport:innerWidth,html:document.documentElement.scrollWidth,body:document.body.scrollWidth}));
  expect(metrics.html).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.body).toBeLessThanOrEqual(metrics.viewport);
}

async function expectTouchTarget(locator){
  const box=await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box.width).toBeGreaterThanOrEqual(44);
  expect(box.height).toBeGreaterThanOrEqual(44);
}

test('FamilyOS uses bundled Nunito without external Google font requests',async({page})=>{
  const externalFonts=[];
  page.on('request',request=>{if(/fonts\.(googleapis|gstatic)\.com/i.test(request.url()))externalFonts.push(request.url())});
  await boot(page);
  const family=await page.evaluate(()=>getComputedStyle(document.body).fontFamily);
  expect(family).toContain('Nunito');
  expect(externalFonts).toEqual([]);
});

test('core task shopping and calendar controls share comfortable touch targets',async({page})=>{
  await boot(page,'/?page=tasks');
  await expectTouchTarget(page.locator('.smart-check').first());
  await expectTouchTarget(page.locator('.global-create-fab'));
  await page.goto('/?page=shopping');await page.waitForLoadState('networkidle');
  await expectTouchTarget(page.locator('.smart-input button').first());
  await page.goto('/?page=calendar');await page.waitForLoadState('networkidle');
  await expectTouchTarget(page.locator('.calendar-filters button').first());
});

test('core FamilyOS screens keep the shared responsive shell without horizontal overflow',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  for(const pageName of ['tasks','shopping','calendar','more','inbox','integrations','automations','notifications','loyalty']){
    await page.goto(`/?page=${pageName}`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.app-shell')).toBeVisible();
    await expectNoOverflow(page);
  }
});
