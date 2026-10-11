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

test('timed end is exclusive at midnight while real cross-midnight spans keep every occupied day',async({page})=>{
 const state=await installApiMocks(page);
 state.events.push(
  {id:'ends-at-midnight',family:state.family.id,source:null,type:'calendar.event',title:'Endet Mitternacht',starts_at:'2026-10-07T23:00:00+02:00',ends_at:'2026-10-08T00:00:00+02:00',actionable:false,payload:{}},
  {id:'crosses-midnight',family:state.family.id,source:null,type:'calendar.event',title:'Über Mitternacht',starts_at:'2026-10-07T23:00:00+02:00',ends_at:'2026-10-08T01:00:00+02:00',actionable:false,payload:{}},
  {id:'multi-day-midnight-end',family:state.family.id,source:null,type:'calendar.event',title:'Mehrtag bis Mitternacht',starts_at:'2026-10-06T12:00:00+02:00',ends_at:'2026-10-09T00:00:00+02:00',actionable:false,payload:{}},
 );
 await page.goto('/?page=calendar&day=2026-10-07');

 const weekDays=page.locator('.calendar-week-day');
 const tuesday=weekDays.nth(1);const wednesday=weekDays.nth(2);const thursday=weekDays.nth(3);const friday=weekDays.nth(4);
 await expect(wednesday.locator('.calendar-event-chip').filter({hasText:'Endet Mitternacht'})).toHaveCount(1);
 await expect(thursday.locator('.calendar-event-chip').filter({hasText:'Endet Mitternacht'})).toHaveCount(0);
 await expect(wednesday.locator('.calendar-event-chip').filter({hasText:'Über Mitternacht'})).toHaveCount(1);
 await expect(thursday.locator('.calendar-event-chip').filter({hasText:'Über Mitternacht'})).toHaveCount(1);
 await expect(tuesday.locator('.calendar-event-chip').filter({hasText:'Mehrtag bis Mitternacht'})).toHaveCount(1);
 await expect(thursday.locator('.calendar-event-chip').filter({hasText:'Mehrtag bis Mitternacht'})).toHaveCount(1);
 await expect(friday.locator('.calendar-event-chip').filter({hasText:'Mehrtag bis Mitternacht'})).toHaveCount(0);

 await page.getByRole('button',{name:'Monat',exact:true}).click();
 await expect(page.locator('.calendar-month-view')).toBeVisible();
 // October 2026 starts on Thursday, so the fixed 42-day grid begins on Monday 28 September.
 const monthDays=page.locator('.calendar-month-day');
 const october7=monthDays.nth(9);const october8=monthDays.nth(10);const october9=monthDays.nth(11);
 await expect(october7.locator('.calendar-event-chip').filter({hasText:'Endet Mitternacht'})).toHaveCount(1);
 await expect(october8.locator('.calendar-event-chip').filter({hasText:'Endet Mitternacht'})).toHaveCount(0);
 await expect(october7.locator('.calendar-event-chip').filter({hasText:'Über Mitternacht'})).toHaveCount(1);
 await expect(october8.locator('.calendar-event-chip').filter({hasText:'Über Mitternacht'})).toHaveCount(1);
 await expect(october8.locator('.calendar-event-chip').filter({hasText:'Mehrtag bis Mitternacht'})).toHaveCount(1);
 await expect(october9.locator('.calendar-event-chip').filter({hasText:'Mehrtag bis Mitternacht'})).toHaveCount(0);
});

test('calendar grids use roving keyboard focus and announce period changes',async({page},testInfo)=>{
 await installApiMocks(page);
 await page.goto('/?page=calendar&day=2026-10-07');

 const period=page.locator('.calendar-period-title');
 await expect(period).toHaveAttribute('aria-live','polite');
 await expect(period).toHaveAttribute('aria-atomic','true');

 if(testInfo.project.name==='mobile-chromium'){
  await expect(page.locator('.calendar-week-mobile')).toBeVisible();
  await expect(page.locator('.calendar-week-grid')).toBeHidden();
  return;
 }

 const weekGrid=page.locator('.calendar-week-grid');
 await expect(weekGrid.locator('.calendar-day-head[tabindex="0"]')).toHaveCount(1);
 const october7=weekGrid.locator('[data-calendar-day="2026-10-07"]');
 await october7.focus();
 await expect(october7).toBeFocused();

 await october7.press('ArrowRight');
 let focused=page.locator('.calendar-week-grid [data-calendar-day="2026-10-08"]');
 await expect(focused).toBeFocused();
 await expect(focused).toHaveAttribute('tabindex','0');
 await expect(weekGrid.locator('.calendar-day-head[tabindex="0"]')).toHaveCount(1);

 await focused.press('ArrowDown');
 focused=page.locator('.calendar-week-grid [data-calendar-day="2026-10-15"]');
 await expect(focused).toBeFocused();
 await focused.press('ArrowUp');
 focused=page.locator('.calendar-week-grid [data-calendar-day="2026-10-08"]');
 await expect(focused).toBeFocused();

 await focused.press('Home');
 focused=page.locator('.calendar-week-grid [data-calendar-day="2026-10-05"]');
 await expect(focused).toBeFocused();
 await focused.press('End');
 await expect(page.locator('.calendar-week-grid [data-calendar-day="2026-10-11"]')).toBeFocused();

 await page.goto('/?page=calendar&view=month&day=2026-10-31');
 const monthGrid=page.locator('.calendar-month-grid');
 await expect(monthGrid.locator('.calendar-month-date[tabindex="0"]')).toHaveCount(1);
 const october31=monthGrid.locator('[data-calendar-day="2026-10-31"]');
 await october31.focus();
 await october31.press('ArrowRight');
 const november1=page.locator('.calendar-month-grid [data-calendar-day="2026-11-01"]');
 await expect(november1).toBeFocused();
 await expect(november1).toHaveAttribute('tabindex','0');
 await expect(page.locator('.calendar-period-title')).toContainText('November');
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
 await expect(compass).toBeVisible();
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
