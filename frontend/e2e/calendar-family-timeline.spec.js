import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function berlinDayKey(value=new Date()){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const part=type=>parts.find(item=>item.type===type)?.value;
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function addCivilDay(key,amount){const [year,month,day]=key.split('-').map(Number);return new Date(Date.UTC(year,month-1,day+amount,12)).toISOString().slice(0,10)}
function event(state,id,title,start,end,participants=[],extra={}){return{id,family:state.family.id,source:null,type:'calendar.event',title,starts_at:start,ends_at:end,participants,actionable:false,is_family_event:false,payload:{location:'',provider:'FamilyOS'},...extra}}
function icsEvent(state,id,title,start,end,participants=[]){return event(state,id,title,start,end,participants,{source:'ics-source-1',source_meta:{id:'ics-source-1',name:'Privater Kalender',kind:'ics',presentation:{tone:'blue'}},payload:{location:'',provider:'ics'}})}

async function expectNoHorizontalPageOverflow(page){const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:window.innerWidth}));expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width+1)}

test('family plan supports people lanes, ICS imports, hiding, rotation and seamless time zoom',async({page})=>{
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
  icsEvent(state,'ics-unassigned','Import ohne Person',`${tuesday}T11:00:00+02:00`,`${tuesday}T12:00:00+02:00`),
  icsEvent(state,'ics-sam','Import mit Sam',`${wednesday}T13:00:00+02:00`,`${wednesday}T14:00:00+02:00`,['member-2']),
 );
 await page.goto(`/?page=calendar&view=timeline&day=${monday}`);
 const planButton=page.getByRole('button',{name:'Plan',exact:true});
 await expect(planButton).toHaveAttribute('aria-pressed','true');
 await expect(page.getByText('Familienplan',{exact:true})).toBeVisible();
 const lanes=page.locator('.family-timeline-lane');
 await expect(lanes).toHaveCount(4);
 const alex=page.locator('[data-lane-id="member-1"]');
 const sam=page.locator('[data-lane-id="member-2"]');
 const family=page.locator('[data-lane-id="__family__"]');
 const imports=page.locator('[data-lane-id="__ics__"]');
 await expect(alex.getByRole('button',{name:/Alex Zahnarzt/})).toBeVisible();
 await expect(sam.getByRole('button',{name:/Sam Training/})).toBeVisible();
 await expect(alex.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(sam.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(family.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(imports.getByRole('button',{name:/Import ohne Person/})).toBeVisible();
 await expect(imports.getByRole('button',{name:/Import mit Sam/})).toHaveCount(0);
 await expect(sam.getByRole('button',{name:/Import mit Sam/})).toBeVisible();
 expect(await alex.evaluate(node=>node.style.getPropertyValue('--lane-color'))).toBe('#2F855A');
 expect(await sam.evaluate(node=>node.style.getPropertyValue('--lane-color'))).toBe('#2563EB');
 const scroll=page.locator('.family-timeline-scroll');
 const beforeZoom=await scroll.evaluate(node=>node.scrollWidth);
 await page.getByRole('slider',{name:/Zeitbereich/}).fill('90');
 await expect.poll(()=>scroll.evaluate(node=>node.scrollWidth)).toBeGreaterThan(beforeZoom);
 await page.locator('.family-timeline-lane-picker summary').click();
 await page.getByRole('checkbox',{name:'Sam',exact:true}).uncheck();
 await expect(page.locator('.family-timeline-lane[data-lane-id="member-2"]')).toHaveCount(0);
 await page.getByRole('button',{name:'Personen als Spalten',exact:true}).click();
 await expect(page.locator('.family-timeline-columns')).toBeVisible();
 await expect(page.locator('.family-timeline-column-head[data-lane-id="member-2"]')).toHaveCount(0);
 await expect(page.locator('.family-timeline-column-head[data-lane-id="__ics__"]')).toContainText('ICS-Importe');
 await page.getByRole('button',{name:'Personen als Zeilen',exact:true}).click();
 await alex.getByRole('button',{name:/Alex Zahnarzt/}).click();
 await expect(page.locator('.calendar-detail')).toContainText('Alex Zahnarzt');
});

test('family plan scrolls internally in both orientations on a 320px viewport without page overflow',async({page})=>{
 await page.setViewportSize({width:320,height:720});
 const state=await installApiMocks(page);
 state.memberships[0].calendar_color='#2F855A';state.memberships[1].calendar_color='#2563EB';
 const day=addCivilDay(berlinDayKey(),1);
 state.events.splice(0,state.events.length,event(state,'mobile-event','Langer Familien-Termin',`${day}T09:00:00+02:00`,`${addCivilDay(day,3)}T18:00:00+02:00`,['member-1','member-2'],{is_family_event:true}),icsEvent(state,'mobile-ics','Importierter Termin',`${day}T12:00:00+02:00`,`${day}T13:00:00+02:00`));
 await page.goto(`/?page=calendar&view=timeline&day=${day}`);
 await expect(page.locator('.family-timeline')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);
 const scroll=page.locator('.family-timeline-scroll');
 const dimensions=await scroll.evaluate(node=>({scrollWidth:node.scrollWidth,clientWidth:node.clientWidth}));
 expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
 await page.getByRole('button',{name:'Personen als Spalten',exact:true}).click();
 await expect(page.locator('.family-timeline-columns')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);
 const rotated=await scroll.evaluate(node=>({scrollWidth:node.scrollWidth,clientWidth:node.clientWidth}));
 expect(rotated.scrollWidth).toBeGreaterThan(rotated.clientWidth);
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Monat',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Plan',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Liste',exact:true})).toBeVisible();
});