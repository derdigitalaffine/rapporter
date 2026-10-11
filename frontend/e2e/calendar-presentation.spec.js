import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function bootCalendar(page,{mobile=false}={}){
 if(mobile)await page.setViewportSize({width:390,height:844});
 await installApiMocks(page);
 await page.goto('/?page=calendar');
}

function berlinDayKey(value=new Date()){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const part=type=>parts.find(item=>item.type===type)?.value;
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function addCivilDay(key,amount){const [year,month,day]=key.split('-').map(Number);const value=new Date(Date.UTC(year,month-1,day+amount,12));return value.toISOString().slice(0,10)}

test('calendar defaults to week and switches week month list without horizontal overflow',async({page})=>{
 await bootCalendar(page,{mobile:true});
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.calendar-week-view')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Monat',exact:true}).click();
 await expect(page.getByRole('button',{name:'Monat',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.calendar-month-view')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Liste',exact:true}).click();
 await expect(page.getByRole('button',{name:'Liste',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page).toHaveURL(/view=list/);
 await expect(page.getByText('Kinderarzt',{exact:true})).toBeVisible();
});

test('calendar view survives a reload through URL state',async({page})=>{
 await bootCalendar(page);
 await page.getByRole('button',{name:'Monat',exact:true}).click();
 await expect(page).toHaveURL(/view=month/);
 await page.reload();
 await expect(page.getByRole('button',{name:'Monat',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.calendar-month-view')).toBeVisible();
});

test('Today week compass navigates weeks, resets to today and opens tapped day in calendar',async({page})=>{
 await installApiMocks(page);
 await page.goto('/');
 const compass=page.getByTestId('week-compass');
 await expect(compass).toBeVisible();
 const heading=compass.getByRole('heading');
 const initial=await heading.textContent();
 await compass.getByRole('button',{name:'Nächste Woche'}).click();
 await expect(heading).not.toHaveText(initial||'');
 await expect(compass.getByRole('button',{name:'Heute',exact:true})).toBeVisible();
 await compass.getByRole('button',{name:'Heute',exact:true}).click();
 await expect(heading).toHaveText(initial||'');
 await compass.locator('.week-compass-days button').first().click();
 await expect(page).toHaveURL(/page=calendar&day=\d{4}-\d{2}-\d{2}/);
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toHaveAttribute('aria-pressed','true');
});

test('Today and mobile calendar distinguish appointments, waste, birthdays and school holidays',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const state=await installApiMocks(page);
 const day=berlinDayKey();const next=addCivilDay(day,1);
 const appointment=state.events.find(event=>event.id==='event-1');
 Object.assign(appointment,{starts_at:`${day}T04:00:00Z`,ends_at:`${day}T05:00:00Z`});
 state.events.push(
  {id:'marker-waste',family:state.family.id,source:'waste-source',type:'waste.collection',title:'Papiertonne',starts_at:`${day}T06:00:00Z`,ends_at:`${day}T07:00:00Z`,actionable:true,payload:{waste_kind:'paper'}},
  {id:'marker-birthday',family:state.family.id,source:null,type:'birthday',title:'Mia: Geburtstag',starts_at:`${day}T12:00:00Z`,ends_at:`${day}T13:00:00Z`,actionable:true,payload:{all_day:true}},
  {id:'marker-holiday',family:state.family.id,source:'school-source',type:'school.holiday',title:'Herbstferien',starts_at:`${day}T00:00:00Z`,ends_at:`${next}T00:00:00Z`,actionable:false,payload:{all_day:true,date_start:day,date_end_exclusive:next}},
 );
 await page.goto('/');
 const compass=page.getByTestId('week-compass');
 await expect(compass.locator('.week-marker.marker-event').first()).toBeVisible();
 await expect(compass.locator('.week-marker.marker-waste.waste-paper')).toBeVisible();
 await expect(compass.locator('.week-marker.marker-birthday')).toBeVisible();
 await expect(compass.locator('.week-compass-days li.has-holiday')).toBeVisible();

 await page.goto('/?page=calendar');
 const strip=page.locator('.calendar-mobile-daystrip');
 await expect(strip).toBeVisible();
 await expect(strip.locator('.calendar-mobile-marker.marker-event').first()).toBeVisible();
 await expect(strip.locator('.calendar-mobile-marker.marker-waste.waste-paper')).toBeVisible();
 await expect(strip.locator('.calendar-mobile-marker.marker-birthday')).toBeVisible();
 await expect(strip.locator('button.has-holiday')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('named ICS sources stay separately visible and filterable',async({page})=>{
 const state=await installApiMocks(page);
 const day=addCivilDay(berlinDayKey(),1);
 state.events.push(
  {id:'ics-parents',family:state.family.id,source:'source-parents',source_name:'Eltern',source_kind:'ics',source_presentation:{icon:'members',color:'green',label:'Elternkalender'},type:'calendar.event',title:'Elterntermin',starts_at:`${day}T10:00:00Z`,ends_at:`${day}T11:00:00Z`,actionable:false,payload:{}},
  {id:'ics-kids',family:state.family.id,source:'source-kids',source_name:'Kinder',source_kind:'ics',source_presentation:{icon:'school',color:'purple',label:'Kinderkalender'},type:'calendar.event',title:'Kindertermin',starts_at:`${day}T12:00:00Z`,ends_at:`${day}T13:00:00Z`,actionable:false,payload:{}},
 );
 await page.goto('/?page=calendar&view=list');
 const parents=page.getByRole('button',{name:'Elternkalender',exact:true});
 const kids=page.getByRole('button',{name:'Kinderkalender',exact:true});
 await expect(parents).toBeVisible();
 await expect(kids).toBeVisible();
 await parents.click();
 await expect(page.getByText('Elterntermin',{exact:true})).toBeVisible();
 await expect(page.getByText('Kindertermin',{exact:true})).toHaveCount(0);
 await page.getByText('Elterntermin',{exact:true}).click();
 await expect(page.getByText('Elternkalender',{exact:true})).toBeVisible();
 await expect(page.getByText('Elternkalender',{exact:true})).toHaveCount(2);
});
