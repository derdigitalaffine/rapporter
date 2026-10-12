import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
}

test('weather hub keeps canonical back action and explicit forecast disclosures',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  const weather={
    current:{temperature:13.4,apparent_temperature:12.1,humidity:74,weather_code:3,precipitation:0,wind_speed:8.2},
    days:[{
      date:'2026-10-11',weather_code:3,temp_max:16,temp_min:9,precipitation_probability:20,precipitation_sum:0.5,
      wind_max:15,wind_gust_max:26,uv_index_max:2,sunrise:'2026-10-11T07:42:00+02:00',sunset:'2026-10-11T18:42:00+02:00'
    }],
    alerts:[],
    source:{location:{label:'Testort'},stale:false,last_success_at:'2026-10-11T12:00:00+02:00'}
  };
  await page.route('**/api/weather/**',async route=>json(route,weather));

  await page.goto('/?page=weather');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading',{name:'Wetter'})).toBeVisible();

  const back=page.getByRole('button',{name:'Zurück'});
  await expect(back).toHaveClass(/\bghost\b/);
  await expect(back).toHaveClass(/\bicon-button\b/);
  await expect(back).toHaveClass(/\bback-button\b/);
  await expect(back).toHaveAttribute('type','button');
  await expectMinTarget(back);

  const day=page.locator('.weather-day > button').first();
  await expect(day).toHaveAttribute('type','button');
  await expect(day).toHaveAttribute('aria-expanded','false');
  await day.click();
  await expect(day).toHaveAttribute('aria-expanded','true');
  await expect(page.locator('.weather-day-details')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await page.setViewportSize({width:1440,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
