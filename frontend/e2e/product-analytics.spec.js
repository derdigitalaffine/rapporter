import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';


test('product analytics pageviews send only normalized route metadata',async({page})=>{
  await installApiMocks(page);
  const events=[];
  await page.route('**/api/analytics/product-event/',async route=>{
    events.push(route.request().postDataJSON());
    await route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({accepted:true})});
  });

  await page.goto('/?page=documents&invite_token=super-secret#reset-secret');
  await expect.poll(()=>events.length).toBeGreaterThan(0);
  expect(events[0]).toEqual({
    kind:'pageview',
    feature:'documents',
    action:'open',
    result:'success',
    route_family:'documents',
    duration_bucket:'none',
  });
  expect(JSON.stringify(events[0])).not.toContain('super-secret');
  expect(JSON.stringify(events[0])).not.toContain('reset-secret');

  await page.evaluate(()=>history.pushState({},'', '/?page=todo&search=private-query#private-fragment'));
  await expect.poll(()=>events.length).toBeGreaterThan(1);
  expect(events.at(-1)).toEqual({
    kind:'pageview',
    feature:'tasks',
    action:'open',
    result:'success',
    route_family:'todo',
    duration_bucket:'none',
  });
  expect(JSON.stringify(events.at(-1))).not.toContain('private-query');
  expect(JSON.stringify(events.at(-1))).not.toContain('private-fragment');
});
