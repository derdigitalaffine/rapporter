import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function berlinDayKey(value=new Date()){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const part=type=>parts.find(item=>item.type===type)?.value;
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function addCivilDay(key,amount){const [year,month,day]=key.split('-').map(Number);return new Date(Date.UTC(year,month-1,day+amount,12)).toISOString().slice(0,10)}

test('native calendar event shows and edits an accessible family member marker',async({page},testInfo)=>{
 const state=await installApiMocks(page);
 const day=addCivilDay(berlinDayKey(),1);
 const event=state.events.find(item=>item.id==='event-1');
 Object.assign(event,{
  starts_at:`${day}T10:00:00+02:00`,
  ends_at:`${day}T11:00:00+02:00`,
  payload:{...event.payload,member_id:'member-2'},
 });
 await page.goto(`/?page=calendar&day=${day}`);

 if(testInfo.project.name!=='mobile-chromium'){
  const chip=page.locator('.calendar-week-grid .calendar-event-chip').filter({hasText:'Kinderarzt'}).first();
  await expect(chip).toBeVisible();
  await expect(chip.locator('[aria-label="Person: Sam"]')).toBeVisible();
 }

 await page.getByRole('button',{name:'Liste',exact:true}).click();
 const row=page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first();
 await expect(row).toContainText('Sam');
 await expect(row.locator('[aria-label="Person: Sam"]')).toBeVisible();
 await row.click();
 await expect(page.locator('.calendar-detail')).toContainText('Person');
 await expect(page.locator('.calendar-detail')).toContainText('Sam');

 await page.locator('.calendar-detail .primary').click();
 const person=page.getByRole('combobox',{name:'Person'});
 await expect(person).toHaveValue('member-2');
 await person.selectOption('member-1');
 await page.locator('.quick-form button.primary').click();

 await expect(page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first()).toContainText('Alex');
 expect(state.events.find(item=>item.id==='event-1')?.payload?.member_id).toBe('member-1');
});

test('unknown member ids are not rendered as names or markers',async({page})=>{
 const state=await installApiMocks(page);
 const day=addCivilDay(berlinDayKey(),1);
 const event=state.events.find(item=>item.id==='event-1');
 Object.assign(event,{
  starts_at:`${day}T10:00:00+02:00`,
  ends_at:`${day}T11:00:00+02:00`,
  payload:{...event.payload,member_id:'removed-member'},
 });
 await page.goto(`/?page=calendar&view=list&day=${day}`);
 const row=page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first();
 await expect(row).toBeVisible();
 await expect(row.locator('[aria-label^="Person:"]')).toHaveCount(0);
 await expect(row).not.toContainText('removed-member');
});
