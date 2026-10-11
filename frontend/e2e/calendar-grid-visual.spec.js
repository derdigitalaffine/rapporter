import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const FIXED_NOW='2026-10-09T12:00:00.000Z';

async function bootCalendarVisual(page,path){
  await page.addInitScript(now=>{const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[now]))}static now(){return new RealDate(now).getTime()} }},FIXED_NOW);
  const state=await installApiMocks(page,{dismissOnboarding:true});
  await page.route('**/api/entitlements/**',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  state.events[0].starts_at='2026-10-08T10:00:00.000Z';
  state.events[0].ends_at='2026-10-08T11:00:00.000Z';
  state.events[1].starts_at='2026-10-09T17:00:00.000Z';
  state.events[1].ends_at='2026-10-09T18:00:00.000Z';
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await page.evaluate(()=>document.fonts.ready.then(()=>true));
  await expect(page.locator('.calendar-agenda')).toBeVisible();
}

async function snapshotCalendarGrid(page,name){
  await expect(page.locator('.calendar-agenda')).toHaveScreenshot(`${name}.png`,{
    animations:'disabled',
    caret:'hide',
    maxDiffPixels:150,
  });
}

test('visual · Calendar week',async({page})=>{
  await bootCalendarVisual(page,'/?page=calendar&day=2026-10-09');
  await expect(page.getByRole('button',{name:'Woche',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.calendar-week-view')).toBeVisible();
  await snapshotCalendarGrid(page,'calendar-week');
});

test('visual · Calendar month',async({page})=>{
  await bootCalendarVisual(page,'/?page=calendar&view=month&day=2026-10-09');
  await expect(page.getByRole('button',{name:'Monat',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.calendar-month-view')).toBeVisible();
  await snapshotCalendarGrid(page,'calendar-month');
});
