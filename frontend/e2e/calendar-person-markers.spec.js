import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function berlinDayKey(value=new Date()){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const part=type=>parts.find(item=>item.type===type)?.value;
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function addCivilDay(key,amount){const [year,month,day]=key.split('-').map(Number);return new Date(Date.UTC(year,month-1,day+amount,12)).toISOString().slice(0,10)}

test('native calendar event shows, edits and persists multiple participant avatars',async({page},testInfo)=>{
 const state=await installApiMocks(page);
 state.memberships[0].calendar_color='#2F855A';
 state.memberships[1].calendar_color='#2563EB';
 state.family.memberships=state.memberships.map(({calendar_color,...member})=>({...member}));
 const day=addCivilDay(berlinDayKey(),1);
 const event=state.events.find(item=>item.id==='event-1');
 Object.assign(event,{
  starts_at:`${day}T10:00:00+02:00`,
  ends_at:`${day}T11:00:00+02:00`,
  participants:['member-2','member-1'],
  is_family_event:true,
 });
 await page.goto(`/?page=calendar&day=${day}`);

 if(testInfo.project.name!=='mobile-chromium'){
  const chip=page.locator('.calendar-week-grid .calendar-event-chip').filter({hasText:'Kinderarzt'}).first();
  await expect(chip).toBeVisible();
  await expect(chip.locator('.calendar-participants[aria-label="Personen: Sam, Alex"]')).toBeVisible();
  await expect(chip.locator('.member-avatar-ui')).toHaveCount(2);
  await expect(chip.locator('.calendar-family-event-badge')).toBeVisible();
 }

 await page.getByRole('button',{name:'Liste',exact:true}).click();
 const row=page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first();
 await expect(row).toContainText('Sam, Alex');
 await expect(row.locator('.calendar-participants')).toBeVisible();
 await expect(row).toContainText('Familientermin');
 await row.click();
 await expect(page.locator('.calendar-detail')).toContainText('Personen');
 await expect(page.locator('.calendar-detail')).toContainText('Sam, Alex');
 await expect(page.locator('.calendar-detail')).toContainText('Familientermin');

 await page.locator('.calendar-detail .primary').click();
 const sam=page.getByRole('checkbox',{name:'Sam',exact:true});
 const alex=page.getByRole('checkbox',{name:'Alex',exact:true});
 await expect(sam).toBeChecked();
 await expect(alex).toBeChecked();
 const samAvatar=page.locator('.event-editor-participant-card').filter({hasText:'Sam'}).locator('.member-avatar-ui');
 const alexAvatar=page.locator('.event-editor-participant-card').filter({hasText:'Alex'}).locator('.member-avatar-ui');
 await expect.poll(()=>samAvatar.evaluate(node=>node.style.getPropertyValue('--member-avatar-color'))).toBe('#2563EB');
 await expect.poll(()=>alexAvatar.evaluate(node=>node.style.getPropertyValue('--member-avatar-color'))).toBe('#2F855A');
 await sam.uncheck();
 await page.locator('.quick-form button.primary').click();

 await expect(page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first()).toContainText('Alex');
 expect(state.events.find(item=>item.id==='event-1')?.participants).toEqual(['member-1']);
 expect(state.events.find(item=>item.id==='event-1')?.payload?.member_id).toBeUndefined();
});

test('legacy member id still renders while unknown participant ids stay anonymous',async({page})=>{
 const state=await installApiMocks(page);
 const day=addCivilDay(berlinDayKey(),1);
 const event=state.events.find(item=>item.id==='event-1');
 Object.assign(event,{
  starts_at:`${day}T10:00:00+02:00`,
  ends_at:`${day}T11:00:00+02:00`,
  payload:{...event.payload,member_id:'member-2'},
 });
 await page.goto(`/?page=calendar&view=list&day=${day}`);
 let row=page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first();
 await expect(row.locator('.calendar-participants[aria-label="Personen: Sam"]')).toBeVisible();

 event.participants=['removed-member'];
 event.payload={...event.payload,member_id:'removed-member'};
 await page.reload();
 row=page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first();
 await expect(row).toBeVisible();
 await expect(row.locator('.calendar-participants')).toHaveCount(0);
 await expect(row).not.toContainText('removed-member');
});
