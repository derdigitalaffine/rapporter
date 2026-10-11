import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const lightCapabilities=['family_management','calendar','todo','shopping','pinboard','notes'];
const premiumCapabilities=[...lightCapabilities,'travel','documents','school','children','pregnancy_baby','pets','advanced_integrations','advanced_tasks'];

async function boot(page,{language='de',snapshot,status=200}={}){
  await installApiMocks(page,{dismissOnboarding:true,language});
  await page.route('**/api/entitlements/**',route=>route.fulfill({
    status,
    contentType:'application/json',
    body:JSON.stringify(snapshot||{detail:'unavailable'}),
  }));
  await page.goto('/?page=more');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('main[data-page="more"]')).toBeVisible();
}

test('entitlements · Light keeps premium roots visible but locked and explained',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await boot(page,{snapshot:{
    family:'family-1',tier:'light',display_name:'Light',capabilities:lightCapabilities,
    origin_summary:'default_light',origins:[],
  }});

  await expect(page.getByText('Familienzugriff',{exact:true})).toBeVisible();
  await expect(page.locator('.entitlement-tier')).toHaveText('Light');
  const travel=page.getByRole('button',{name:/Reisen.*Premium.*gesperrt/i});
  await expect(travel).toBeVisible();
  const box=await travel.boundingBox();
  expect(box?.height||0).toBeGreaterThanOrEqual(44);
  await travel.click();
  await expect(page.locator('main[data-page="more"]')).toBeVisible();
  await expect(page.getByText(/Reisen ist mit Light nicht freigeschaltet/)).toBeVisible();
  const width=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
  expect(width.scroll).toBeLessThanOrEqual(width.client+1);
});

test('entitlements · VIP remains fully unlocked and navigates normally in English',async({page})=>{
  await boot(page,{language:'en',snapshot:{
    family:'family-1',tier:'vip',display_name:'VIP',capabilities:premiumCapabilities,
    origin_summary:'legacy_grandfathered',origins:['legacy_grandfathered'],
  }});

  await expect(page.getByText('Family access',{exact:true})).toBeVisible();
  await expect(page.locator('.entitlement-tier')).toHaveText('VIP');
  await expect(page.locator('.entitlement-lock-badge')).toHaveCount(0);
  await page.getByRole('button',{name:'Trips',exact:true}).click();
  await expect(page.locator('main[data-page="trips"]')).toBeVisible();
});

test('entitlements · snapshot failure fails open instead of inventing a client-side paywall',async({page})=>{
  await boot(page,{status:503});

  await expect(page.getByText('Familienzugriff',{exact:true})).toHaveCount(0);
  await expect(page.locator('.entitlement-lock-badge')).toHaveCount(0);
  await page.getByRole('button',{name:'Reisen',exact:true}).click();
  await expect(page.locator('main[data-page="trips"]')).toBeVisible();
});
