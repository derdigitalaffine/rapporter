import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function addProjectedWeatherEvent(state){
 state.events.push({
  id:'weather-source-event',
  family:state.family.id,
  source:'integration-1',
  source_meta:{id:'integration-1',name:'Open-Meteo',kind:'weather',presentation:{icon:'weather',tone:'blue',label:'Open-Meteo'}},
  type:'weather.forecast',
  title:'Wetter morgen',
  starts_at:new Date(Date.now()+4*3600000).toISOString(),
  ends_at:new Date(Date.now()+5*3600000).toISOString(),
  actionable:false,
  payload:{provider:'open_meteo'},
 });
}

test('calendar surfaces a projected source sync error without leaking raw error details',async({page})=>{
 const state=await installApiMocks(page);
 addProjectedWeatherEvent(state);

 await page.goto('/?page=calendar');
 const notice=page.locator('.calendar-source-health');
 await expect(notice).toBeVisible();
 await expect(notice).toHaveAttribute('role','status');
 await expect(notice).toContainText('Eine Kalenderquelle braucht Aufmerksamkeit');
 await expect(notice).toContainText('Open-Meteo');
 await expect(notice).not.toContainText('Zeitüberschreitung beim Abruf');

 const link=notice.getByRole('link',{name:'Integrationen öffnen'});
 await expect(link).toBeVisible();
 await link.click();
 await expect(page).toHaveURL(/page=integrations/);
 await expect(page.getByRole('heading',{name:'Integrationen',exact:true})).toBeVisible();
});

test('calendar health hint only follows active projected sources and localizes to English',async({page})=>{
 const state=await installApiMocks(page,{language:'en'});
 addProjectedWeatherEvent(state);
 state.integrations.push({id:'unused-error',family:state.family.id,name:'Unused calendar',kind:'ics',enabled:true,last_sync_status:'error',last_sync_error:'secret raw error'});

 await page.goto('/?page=calendar');
 const notice=page.locator('.calendar-source-health');
 await expect(notice).toContainText('One calendar source needs attention');
 await expect(notice).toContainText('Open-Meteo');
 await expect(notice).not.toContainText('Unused calendar');
 await expect(notice).not.toContainText('secret raw error');
 await expect(notice.getByRole('link',{name:'Open integrations'})).toBeVisible();

 state.integrations[0].last_sync_status='success';
 await page.reload();
 await expect(page.locator('.calendar-source-health')).toHaveCount(0);
});
