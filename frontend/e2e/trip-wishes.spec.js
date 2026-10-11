import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const FIXED_NOW='2026-10-10T12:00:00.000Z';

async function freezeToday(page){
 await page.addInitScript(now=>{const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[now]))}static now(){return new RealDate(now).getTime()} }},FIXED_NOW);
}

async function mockTrips(page,rows){
 await page.route('**/api/trips/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(rows)}));
}

const wish=(id,title,extra={})=>({
 id,family:'family-1',title,destination:'',stage:'planning',date_precision:'season',date_year:2028,date_month:null,date_season:'summer',starts_on:null,ends_on:null,archived:false,photos:[],...extra,
});
const concrete=(id,title,extra={})=>({
 id,family:'family-1',title,destination:'Berlin',stage:'scheduled',date_precision:'exact',starts_on:'2026-10-13',ends_on:'2026-10-17',archived:false,photos:[],...extra,
});

test('trip wishes stay out of Today until the private widget opt-in is saved',async({page})=>{
 await freezeToday(page);
 await installApiMocks(page,{dismissOnboarding:true});
 await mockTrips(page,[wish('wish-1','Sommer in Italien')]);
 await page.goto('/');
 await expect(page.getByRole('button',{name:'Anpassen'})).toBeEnabled();
 await expect(page.getByTestId('today-trip-banner')).toHaveCount(0);

 await page.getByRole('button',{name:'Anpassen'}).click();
 const editor=page.getByRole('region',{name:'Anpassen'});
 const toggle=editor.getByLabel('Reisewünsche anzeigen');
 await expect(toggle).not.toBeChecked();
 await toggle.check();
 await expect(page.getByTestId('today-trip-banner')).toContainText('Reisewunsch');
 await expect(page.getByTestId('today-trip-banner')).toContainText('Sommer in Italien');
 await expect(page.getByTestId('today-trip-banner')).toContainText('In Planung');
 await page.getByRole('button',{name:'Speichern'}).click();
 await expect(page.getByRole('region',{name:'Anpassen'})).toHaveCount(0);
 await expect(page.getByTestId('today-trip-banner')).toContainText('Sommer in Italien');
});

test('a concrete upcoming trip keeps priority even when wishes are enabled',async({page})=>{
 await freezeToday(page);
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.todayLayout.widgets.push({id:'trip',visible:true,size:'full',settings:{show_wishes:true}});
 await mockTrips(page,[wish('wish-1','Sommer in Italien'),concrete('trip-1','Herbstferien')]);
 await page.goto('/');
 const banner=page.getByTestId('today-trip-banner');
 await expect(banner).toContainText('Nächste Reise');
 await expect(banner).toContainText('Herbstferien');
 await expect(banner).toContainText('Noch 3 Tage');
 await expect(banner).not.toContainText('Sommer in Italien');
});
