import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function event(state,id,title,startsAt,endsAt){
 return {
  id,
  family:state.family.id,
  source:null,
  type:'calendar.event',
  title,
  starts_at:startsAt,
  ends_at:endsAt,
  actionable:false,
  payload:{},
 };
}

async function expectNoHorizontalPageOverflow(page){
 await expect.poll(()=>page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:window.innerWidth}))).toEqual(
  expect.objectContaining({scroll:expect.any(Number),width:expect.any(Number)}),
 );
 const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:window.innerWidth}));
 expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width+1);
}

test('calendar reflows at 320/390 and a 200%-zoom-equivalent width without horizontal overflow',async({page})=>{
 await page.setViewportSize({width:320,height:720});
 await installApiMocks(page);
 await page.goto('/?page=calendar');
 await expect(page.locator('.calendar-week-mobile')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);

 const narrowDay=await page.locator('.calendar-mobile-daystrip button').first().boundingBox();
 expect(narrowDay?.width||0).toBeGreaterThanOrEqual(44);
 expect(narrowDay?.height||0).toBeGreaterThanOrEqual(44);

 await page.getByRole('button',{name:'Monat',exact:true}).click();
 await expect(page.locator('.calendar-month-view')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);

 await page.setViewportSize({width:390,height:844});
 await page.getByRole('button',{name:'Woche',exact:true}).click();
 await expect(page.locator('.calendar-week-mobile')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);

 // 512 CSS px corresponds to a common 1024px desktop viewport at 200% browser zoom.
 await page.setViewportSize({width:512,height:640});
 await expect(page.locator('.calendar-week-mobile')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);
 const zoomDay=await page.locator('.calendar-mobile-daystrip button').first().boundingBox();
 expect(zoomDay?.width||0).toBeGreaterThanOrEqual(44);
});

test('dense week stays bounded while selected day exposes every event including multi-day entries',async({page})=>{
 await page.setViewportSize({width:1100,height:800});
 const state=await installApiMocks(page);
 state.events.splice(0,state.events.length);
 state.events.push(
  event(state,'dense-1','Frühstück','2026-10-07T06:30:00+02:00','2026-10-07T07:00:00+02:00'),
  event(state,'dense-2','Schule','2026-10-07T08:00:00+02:00','2026-10-07T09:00:00+02:00'),
  event(state,'dense-3','Arzt','2026-10-07T09:30:00+02:00','2026-10-07T10:15:00+02:00'),
  event(state,'dense-4','Einkauf','2026-10-07T11:00:00+02:00','2026-10-07T11:30:00+02:00'),
  event(state,'dense-5','Abholen','2026-10-07T13:00:00+02:00','2026-10-07T13:30:00+02:00'),
  event(state,'dense-6','Training','2026-10-07T15:00:00+02:00','2026-10-07T16:00:00+02:00'),
  event(state,'dense-7','Elternabend','2026-10-07T18:00:00+02:00','2026-10-07T19:00:00+02:00'),
  event(state,'dense-multi','Familienbesuch','2026-10-06T17:00:00+02:00','2026-10-08T09:00:00+02:00'),
 );
 await page.goto('/?page=calendar&day=2026-10-07');

 const wednesday=page.locator('.calendar-week-day').filter({has:page.locator('[data-calendar-day="2026-10-07"]')});
 await expect(wednesday.locator('.calendar-event-chip')).toHaveCount(5);
 await expect(wednesday.locator('.calendar-more')).toHaveText('+3');
 await expect(wednesday).toContainText('Familienbesuch');

 const selected=page.locator('.calendar-selected-events');
 await expect(selected.locator('.calendar-event-chip')).toHaveCount(8);
 await expect(selected.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expectNoHorizontalPageOverflow(page);

 await page.setViewportSize({width:320,height:720});
 await expect(page.locator('.calendar-week-grid')).toBeHidden();
 await expect(page.locator('.calendar-week-mobile')).toBeVisible();
 await expect(selected.locator('.calendar-event-chip')).toHaveCount(8);
 await expectNoHorizontalPageOverflow(page);
});
