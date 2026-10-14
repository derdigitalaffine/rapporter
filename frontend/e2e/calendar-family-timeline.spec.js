import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function berlinDayKey(value=new Date()){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const part=type=>parts.find(item=>item.type===type)?.value;
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function addCivilDay(key,amount){const [year,month,day]=key.split('-').map(Number);return new Date(Date.UTC(year,month-1,day+amount,12)).toISOString().slice(0,10)}
function event(state,id,title,start,end,participants=[],extra={}){return{id,family:state.family.id,source:null,type:'calendar.event',title,starts_at:start,ends_at:end,participants,actionable:false,is_family_event:false,payload:{location:'',provider:'FamilyOS'},...extra}}

async function expectNoHorizontalPageOverflow(page){const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:window.innerWidth}));expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width+1)}

test('family plan groups appointments by member and keeps shared events visible',async({page})=>{
 const state=await installApiMocks(page);
 state.memberships[0].calendar_color='#2F855A';
 state.memberships[1].calendar_color='#2563EB';
 const monday=addCivilDay(berlinDayKey(),1);
 const tuesday=addCivilDay(monday,1);
 const wednesday=addCivilDay(monday,2);
 state.events.splice(0,state.events.length,
  event(state,'alex-event','Alex Zahnarzt',`${monday}T09:00:00+02:00`,`${monday}T10:00:00+02:00`,['member-1'],{payload:{location:'Praxis',provider:'FamilyOS'}}),
  event(state,'sam-event','Sam Training',`${tuesday}T16:00:00+02:00`,`${tuesday}T18:00:00+02:00`,['member-2']),
  event(state,'shared-event','Familienbesuch',`${monday}T17:00:00+02:00`,`${wednesday}T09:00:00+02:00`,['member-1','member-2'],{is_family_event:true}),
 );
 await page.goto(`/?page=calendar&view=timeline&day=${monday}`);
 const planButton=page.getByRole('button',{name:'Plan',exact:true});
 await expect(planButton).toHaveAttribute('aria-pressed','true');
 await expect(page.getByText('Familienplan',{exact:true})).toBeVisible();
 const lanes=page.locator('.family-timeline-lane');
 await expect(lanes).toHaveCount(3);
 const alex=lanes.filter({has:page.getByText('Alex',{exact:true})});
 const sam=lanes.filter({has:page.getByText('Sam',{exact:true})});
 const family=lanes.filter({has:page.getByText('Musterfamilie',{exact:true})});
 await expect(alex.getByRole('button',{name:/Alex Zahnarzt/})).toBeVisible();
 await expect(sam.getByRole('button',{name:/Sam Training/})).toBeVisible();
 await expect(alex.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(sam.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(family.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 expect(await alex.evaluate(node=>node.style.getPropertyValue('--lane-color'))).toBe('#2F855A');
 expect(await sam.evaluate(node=>node.style.getPropertyValue('--lane-color'))).toBe('#2563EB');
 await alex.getByRole('button',{name:/Alex Zahnarzt/}).click();
 await expect(page.locator('.calendar-detail')).toContainText('Alex Zahnarzt');
 await page.locator('.calendar-detail .sheet-close').click();
 await page.getByRole('button',{name:'Woche',exact:true}).click();
 await expect(page.locator('.calendar-week-view')).toBeVisible();
 await planButton.click();
 await expect(page.locator('.family-timeline')).toBeVisible();
});

test('family plan scrolls internally on a 320px viewport without page overflow',async({page})=>{
 await page.setViewportSize({width:320,height:720});
 const state=await installApiMocks(page);
 state.memberships[0].calendar_color='#2F855A';state.memberships[1].calendar_color='#2563EB';
 const day=addCivilDay(berlinDayKey(),1);
 state.events.splice(0,state.events.length,event(state,'mobile-event','Langer Familien-Termin',`${day}T09:00:00+02:00`,`${addCivilDay(day,3)}T18:00:00+02:00`,['member-1','member-2'],{is_family_event:true}));
 await page.goto(`/?page=calendar&view=timeline&day=${day}`);
 await expect(page.locator('.family-timeline')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);
 const scroll=page.locator('.family-timeline-scroll');
 const dimensions=await scroll.evaluate(node=>({scrollWidth:node.scrollWidth,clientWidth:node.clientWidth}));
 expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Monat',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Plan',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Liste',exact:true})).toBeVisible();
});