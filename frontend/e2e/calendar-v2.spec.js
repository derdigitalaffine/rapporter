import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function bootCalendar(page,{mobile=false}={}){
 if(mobile)await page.setViewportSize({width:390,height:844});
 const state=await installApiMocks(page);
 state.integrations.push({id:'calendar-source-1',family:state.family.id,name:'Kita',kind:'ics',enabled:true,endpoint:'',config:{adapter:'ics',appearance:{color:'purple',icon:'heart'}},last_sync_status:'success'});
 state.events.push({id:'ics-event-1',family:state.family.id,source:'calendar-source-1',type:'calendar.event',title:'Kita-Fest',starts_at:new Date(Date.now()+26*3600000).toISOString(),ends_at:new Date(Date.now()+28*3600000).toISOString(),actionable:false,payload:{provider:'Kita',location:'Turnhalle',description:'',all_day:false,recurring:true}});
 await page.goto('/?page=calendar');
 return state;
}

test('calendar defaults to week and switches week month list without horizontal overflow',async({page})=>{
 await bootCalendar(page,{mobile:true});
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'Monat',exact:true}).click();
 await expect(page.getByRole('button',{name:'Monat',exact:true})).toHaveAttribute('aria-pressed','true');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Liste',exact:true}).click();
 await expect(page.getByRole('button',{name:'Liste',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByText('Kinderarzt',{exact:true})).toBeVisible();
 await expect(page.getByText('Kita-Fest',{exact:true})).toBeVisible();
});

test('calendar source filter uses configured source name icon appearance and can be toggled',async({page})=>{
 await bootCalendar(page);
 const source=page.locator('.calendar-source-chip').filter({hasText:'Kita'});
 await expect(source).toBeVisible();
 await expect(source).toHaveAttribute('aria-pressed','true');
 await source.click();
 await expect(source).toHaveAttribute('aria-pressed','false');
 await expect(page.getByText('Kita-Fest',{exact:true})).toHaveCount(0);
 await source.click();
 await expect(page.getByText('Kita-Fest',{exact:true}).first()).toBeVisible();
});

test('Today week compass navigates weeks, resets to today and opens tapped day in calendar',async({page})=>{
 await installApiMocks(page);
 await page.goto('/');
 const compass=page.getByTestId('week-compass');
 await expect(compass).toBeVisible();
 const initial=await compass.getByRole('heading').textContent();
 await compass.getByRole('button',{name:'Nächste Woche'}).click();
 await expect(compass.getByRole('heading')).not.toHaveText(initial||'');
 await expect(compass.getByRole('button',{name:'Heute',exact:true})).toBeVisible();
 await compass.getByRole('button',{name:'Heute',exact:true}).click();
 await expect(compass.getByRole('heading')).toHaveText(initial||'');
 await compass.locator('.week-compass-days button').first().click();
 await expect(page).toHaveURL(/page=calendar&day=\d{4}-\d{2}-\d{2}/);
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toHaveAttribute('aria-pressed','true');
});

test('waste collection appears only once on Today',async({page})=>{
 const state=await installApiMocks(page);
 state.events.push({id:'waste-today-1',family:state.family.id,source:'waste-source-1',type:'waste.collection',title:'Restmüll',starts_at:new Date(Date.now()+2*3600000).toISOString(),ends_at:null,actionable:true,payload:{provider:'Abfallkalender',waste_type:'rest'}});
 await page.goto('/');
 await expect(page.getByText('Restmüll',{exact:true})).toHaveCount(1);
});
