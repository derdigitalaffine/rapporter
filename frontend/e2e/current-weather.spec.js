import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('Today shows current weather conditions separately from upcoming events',async({page})=>{
  const state=await installApiMocks(page,{authenticated:true,language:'de',dismissOnboarding:true});
  state.events.unshift({
    id:'weather-current',
    family:'family-1',
    source:'integration-1',
    type:'weather.current',
    title:'13.4 °C',
    starts_at:new Date(Date.now()-5*60*1000).toISOString(),
    ends_at:null,
    actionable:false,
    payload:{
      provider:'Open-Meteo',
      temperature:13.4,
      apparent_temperature:12.1,
      humidity:74,
      weather_code:3,
      precipitation:0,
      wind_speed:8.2,
    },
  });

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const weather=page.getByTestId('current-weather');
  await expect(weather).toBeVisible();
  await expect(weather).toContainText('13.4 °C');
  await expect(weather).toContainText('Bewölkt');
  await expect(weather).toContainText('Gefühlt 12.1 °C');
  await expect(weather).toContainText('Wind 8.2 km/h');
  await expect(weather).toContainText('Open-Meteo');

  const next=page.getByTestId('today-context');
  await expect(next).toContainText('Kinderarzt');
  await expect(next).not.toContainText('13.4 °C');
});
