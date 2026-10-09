import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body)=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});

test('Today shows current weather as a teaser and opens the dedicated weather page',async({page})=>{
  const state=await installApiMocks(page,{authenticated:true,language:'de',dismissOnboarding:true});
  const weather={
    source:{id:'integration-1',provider:'Open-Meteo',last_success_at:new Date().toISOString(),last_sync_status:'success',last_sync_error:'',stale:false,location:{label:'Kaiserslautern'}},
    current:{observed_at:new Date(Date.now()-5*60*1000).toISOString(),temperature:13.4,apparent_temperature:12.1,humidity:74,weather_code:3,precipitation:0,wind_speed:8.2},
    days:[{date:new Date().toISOString().slice(0,10),weather_code:3,temp_min:8.4,temp_max:15.2,precipitation_probability:20,precipitation_sum:0,wind_max:18,wind_gust_max:31,sunrise:null,sunset:null,uv_index_max:2.1}],
    alerts:[],
  };
  await page.route('**/api/dashboard/**',route=>json(route,{tasks:state.tasks,task_lists:state.taskLists,events:state.events,routines:state.routines,shopping_lists:state.shoppingLists,inbox_count:0,automation_count:0,weather}));
  await page.route('**/api/weather/**',route=>json(route,weather));

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const teaser=page.getByTestId('current-weather');
  await expect(teaser).toBeVisible();
  await expect(teaser).toContainText('13,4 °C');
  await expect(teaser).toContainText('Bewölkt');
  await expect(teaser).toContainText('Gefühlt 12,1 °C');
  await expect(teaser).toContainText('Wind 8,2 km/h');
  await expect(teaser).toContainText('Open-Meteo');

  const next=page.getByRole('heading',{name:'Als Nächstes'}).locator('..').locator('..');
  await expect(next).toContainText('Kinderarzt');
  await expect(next).not.toContainText('13,4 °C');

  await teaser.getByRole('button').click();
  await expect(page).toHaveURL(/page=weather/);
  await expect(page.getByRole('heading',{name:'Wetter',exact:true})).toBeVisible();
});
