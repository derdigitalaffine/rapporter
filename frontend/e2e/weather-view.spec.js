import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const days=Array.from({length:7},(_,index)=>({
  date:`2026-10-${String(9+index).padStart(2,'0')}`,
  weather_code:[3,61,2,0,80,45,95][index],
  temp_min:[8.4,7.2,6.8,7,8.1,5.4,4.9][index],
  temp_max:[15.2,14.1,16,17.4,12.8,11.2,10.5][index],
  apparent_temp_min:6+index/10,
  apparent_temp_max:13+index/10,
  precipitation_probability:[20,65,15,5,80,30,70][index],
  precipitation_sum:[0,4.2,0,0,7.1,.4,5.8][index],
  wind_max:[18,21,14,11,24,13,32][index],
  wind_gust_max:[31,38,26,20,44,28,58][index],
  sunrise:`2026-10-${String(9+index).padStart(2,'0')}T07:35:00+02:00`,
  sunset:`2026-10-${String(9+index).padStart(2,'0')}T18:45:00+02:00`,
  uv_index_max:2.1,
}));

const weather={
  source:{id:'integration-1',provider:'Open-Meteo',last_success_at:'2026-10-09T17:55:00Z',last_attempt_at:'2026-10-09T18:00:00Z',last_sync_status:'error',last_sync_error:'Zeitüberschreitung',stale:true,location:{latitude:49.44,longitude:7.77,label:'Kaiserslautern'}},
  current:{observed_at:'2026-10-09T17:55:00Z',temperature:13.4,apparent_temperature:12.1,weather_code:3,humidity:74,precipitation:0,wind_speed:8.2},
  days,
  alerts:[{id:'warning-1',title:'Amtliche WARNUNG vor STURMBÖEN',starts_at:'2026-10-09T17:00:00Z',ends_at:'2026-10-09T22:00:00Z',region:'Kaiserslautern',level:3,description:'Es treten Sturmböen auf.',instruction:'Lose Gegenstände sichern.',provider:'DWD'}],
};

async function boot(page,viewport){
  await page.setViewportSize(viewport);
  await installApiMocks(page,{authenticated:true,language:'de',dismissOnboarding:true});
  await page.route('**/api/weather/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(weather)}));
  await page.goto('/?page=weather');
  await expect(page.getByRole('heading',{name:'Wetter',exact:true})).toBeVisible();
}

for(const viewport of [{width:390,height:844},{width:1024,height:768},{width:1440,height:900}]){
  test(`weather renders seven days without horizontal overflow at ${viewport.width}x${viewport.height}`,async({page})=>{
    await boot(page,viewport);
    await expect(page.getByTestId('weather-current-detail')).toContainText('13,4 °C');
    await expect(page.getByText('Amtliche WARNUNG vor STURMBÖEN')).toBeVisible();
    await expect(page.getByText('Nicht aktuell',{exact:true})).toBeVisible();
    await expect(page.getByTestId('weather-day')).toHaveCount(7);
    await page.getByTestId('weather-day').nth(1).click();
    await expect(page.getByTestId('weather-day-detail')).toContainText('4,2 mm');
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}
