import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function berlinDayKey(value=new Date()){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const part=type=>parts.find(item=>item.type===type)?.value;
 return `${part('year')}-${part('month')}-${part('day')}`;
}
function currentWeekMonday(){const [year,month,day]=berlinDayKey().split('-').map(Number);const value=new Date(Date.UTC(year,month-1,day,12));const offset=(value.getUTCDay()+6)%7;value.setUTCDate(value.getUTCDate()-offset);return value.toISOString().slice(0,10)}
function addCivilDay(key,amount){const [year,month,day]=key.split('-').map(Number);return new Date(Date.UTC(year,month-1,day+amount,12)).toISOString().slice(0,10)}
function event(state,id,title,start,end,participants=[],extra={}){return{id,family:state.family.id,source:null,type:'calendar.event',title,starts_at:start,ends_at:end,participants,actionable:false,is_family_event:false,payload:{location:'',provider:'FamilyOS'},...extra}}
function icsEvent(state,id,title,start,end,participants=[]){return event(state,id,title,start,end,participants,{source:'ics-source-1',source_meta:{id:'ics-source-1',name:'Privater Kalender',kind:'ics',presentation:{tone:'blue'}},payload:{location:'',provider:'ics'}})}
async function mockCurrentProfile(page,state){await page.route('**/api/profile/?family=*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({user_id:1,membership_id:'member-1',family:state.family.id,display_name:'Alex',role:'owner',calendar_color:'#2F855A'})}))}
async function mockPlannerPreferences(page,state){let laneOrder=[];await page.route('**/api/calendar-planner-preferences/**',async route=>{const request=route.request();const method=request.method();if(method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({family:state.family.id,lane_order:laneOrder})});if(method==='PATCH'){const body=request.postDataJSON();laneOrder=Array.isArray(body?.lane_order)?body.lane_order.map(String):[];return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({family:state.family.id,lane_order:laneOrder})})}return route.fallback()});return{get laneOrder(){return laneOrder}}}
async function expectNoHorizontalPageOverflow(page){const dimensions=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:window.innerWidth}));expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width+1)}

test('family plan supports ordering, persistence, imports, timed positioning, 2-30 day zoom and lane height',async({page})=>{
 const state=await installApiMocks(page);await mockCurrentProfile(page,state);const plannerPreferences=await mockPlannerPreferences(page,state);
 state.memberships[0].calendar_color='#2F855A';
 state.memberships[1].calendar_color='#2563EB';
 const monday=currentWeekMonday();
 const tuesday=addCivilDay(monday,1);
 const wednesday=addCivilDay(monday,2);
 state.events.splice(0,state.events.length,
  event(state,'alex-event','Alex Zahnarzt',`${monday}T09:00:00+02:00`,`${monday}T10:00:00+02:00`,['member-1'],{payload:{location:'Praxis',provider:'FamilyOS'}}),
  event(state,'alex-overlap','Alex Parallel',`${monday}T09:30:00+02:00`,`${monday}T10:30:00+02:00`,['member-1']),
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
 const dentist=alex.getByRole('button',{name:/Alex Zahnarzt/});
 const parallel=alex.getByRole('button',{name:/Alex Parallel/});
 await expect(dentist).toBeVisible();
 await expect(parallel).toBeVisible();
 await expect(alex.getByLabel(/1 Überschneidung/)).toBeVisible();
 const dentistOffsets=await dentist.evaluate(node=>({start:Number(node.dataset.startOffset),end:Number(node.dataset.endOffset)}));
 const parallelOffsets=await parallel.evaluate(node=>({start:Number(node.dataset.startOffset),end:Number(node.dataset.endOffset)}));
 expect(dentistOffsets.start).toBeGreaterThan(0);
 expect(dentistOffsets.start).toBeLessThan(1);
 expect(dentistOffsets.end-dentistOffsets.start).toBeCloseTo(1/24,3);
 expect(parallelOffsets.start).toBeGreaterThan(dentistOffsets.start);
 expect(parallelOffsets.start).toBeLessThan(dentistOffsets.end);
 await expect(sam.getByRole('button',{name:/Sam Training/})).toBeVisible();
 await expect(alex.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(sam.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(family.getByRole('button',{name:/Familienbesuch/})).toBeVisible();
 await expect(imports.getByRole('button',{name:/Import ohne Person/})).toBeVisible();
 await expect(imports.getByRole('button',{name:/Import mit Sam/})).toHaveCount(0);
 await expect(sam.getByRole('button',{name:/Import mit Sam/})).toBeVisible();
 await expect(page.locator('.family-timeline-day-head')).toHaveCount(30);
 await expect(page.locator('.family-timeline-day-head.is-weekend')).toHaveCount(8);
 await expect(page.locator('.family-timeline-now-marker')).toHaveCount(4);
 expect(await alex.evaluate(node=>node.style.getPropertyValue('--lane-color'))).toBe('#2F855A');
 expect(await sam.evaluate(node=>node.style.getPropertyValue('--lane-color'))).toBe('#2563EB');
 const scroll=page.locator('.family-timeline-scroll');
 const table=page.locator('.family-timeline-rows');
 const zoom=page.getByRole('slider',{name:/Zeitbereich/});
 await expect(zoom).toHaveAttribute('min','2');
 await expect(zoom).toHaveAttribute('max','30');
 await expect(zoom).toHaveValue('7');
 const defaultDayWidth=Number(await table.evaluate(node=>parseFloat(node.style.getPropertyValue('--timeline-day-width'))));
 const beforeZoom=await scroll.evaluate(node=>node.scrollWidth);
 await zoom.fill('2');
 const twoDayWidth=Number(await table.evaluate(node=>parseFloat(node.style.getPropertyValue('--timeline-day-width'))));
 expect(twoDayWidth).toBeGreaterThan(defaultDayWidth*2.5);
 await expect.poll(()=>scroll.evaluate(node=>node.scrollWidth)).toBeGreaterThan(beforeZoom*2.5);
 await zoom.fill('30');
 const thirtyDayWidth=Number(await table.evaluate(node=>parseFloat(node.style.getPropertyValue('--timeline-day-width'))));
 expect(thirtyDayWidth).toBeLessThan(defaultDayWidth/3);
 const rowHeight=page.getByRole('slider',{name:/Zeilenhöhe/});
 const defaultHeight=Number(await family.evaluate(node=>parseFloat(node.style.getPropertyValue('--timeline-lane-height'))));
 expect(defaultHeight).toBeGreaterThanOrEqual(70);
 await rowHeight.fill('0');
 const compactHeight=Number(await family.evaluate(node=>parseFloat(node.style.getPropertyValue('--timeline-lane-height'))));
 expect(compactHeight).toBeLessThan(defaultHeight);
 await rowHeight.fill('100');
 const roomyHeight=Number(await family.evaluate(node=>parseFloat(node.style.getPropertyValue('--timeline-lane-height'))));
 expect(roomyHeight).toBeGreaterThan(defaultHeight);

 await page.locator('.family-timeline-lane-picker summary').click();
 await expect(page.getByPlaceholder('Personen und Bereiche suchen')).toBeVisible();
 await page.getByRole('button',{name:'Sam nach oben verschieben'}).click();
 await expect(lanes.nth(0)).toHaveAttribute('data-lane-id','member-2');
 await expect.poll(()=>plannerPreferences.laneOrder[0]).toBe('member-2');
 await expect.poll(()=>page.evaluate(()=>JSON.parse(localStorage.getItem('familyos:calendar:timeline:v3:family-1:member-1')||'{}').laneOrder?.[0])).toBe('member-2');
 await page.evaluate(()=>localStorage.removeItem('familyos:calendar:timeline:v3:family-1:member-1'));
 await page.reload();
 await expect(page.locator('.family-timeline-lane').nth(0)).toHaveAttribute('data-lane-id','member-2');

 await page.locator('.family-timeline-lane-picker summary').click();
 await page.getByRole('checkbox',{name:'Sam',exact:true}).uncheck();
 await expect(page.locator('.family-timeline-lane[data-lane-id="member-2"]')).toHaveCount(0);
 await page.getByRole('button',{name:'Personen als Spalten',exact:true}).click();
 await expect(page.locator('.family-timeline-columns')).toBeVisible();
 await expect(page.locator('.family-timeline-column-head[data-lane-id="member-2"]')).toHaveCount(0);
 await expect(page.locator('.family-timeline-column-head[data-lane-id="__ics__"]')).toContainText('ICS-Importe');
 await page.getByRole('button',{name:'Personen als Zeilen',exact:true}).click();
 await page.locator('.family-timeline-lane[data-lane-id="member-1"]').getByRole('button',{name:/Alex Zahnarzt/}).click();
 await expect(page.locator('.calendar-detail')).toContainText('Alex Zahnarzt');
});

test('family plan can hide empty lanes and keeps controls inside a 320px viewport',async({page})=>{
 await page.setViewportSize({width:320,height:720});
 const state=await installApiMocks(page);await mockCurrentProfile(page,state);await mockPlannerPreferences(page,state);
 state.memberships[0].calendar_color='#2F855A';state.memberships[1].calendar_color='#2563EB';
 state.memberships.push({id:'member-3',family:state.family.id,user:3,username:'lee',role:'adult',display_name:'Lee',avatar:'',calendar_color:'#7C3AED'});state.family.memberships=state.memberships;
 const day=addCivilDay(berlinDayKey(),1);
 state.events.splice(0,state.events.length,event(state,'mobile-event','Langer Familien-Termin',`${day}T09:00:00+02:00`,`${addCivilDay(day,3)}T18:00:00+02:00`,['member-1','member-2'],{is_family_event:true}),icsEvent(state,'mobile-ics','Importierter Termin',`${day}T12:00:00+02:00`,`${day}T13:00:00+02:00`));
 await page.goto(`/?page=calendar&view=timeline&day=${day}`);
 await expect(page.locator('.family-timeline')).toBeVisible();
 await expect(page.locator('.family-timeline-lane[data-lane-id="member-3"]')).toBeVisible();
 await expectNoHorizontalPageOverflow(page);
 const scroll=page.locator('.family-timeline-scroll');
 await page.getByRole('slider',{name:/Zeitbereich/}).fill('2');
 const dimensions=await scroll.evaluate(node=>({scrollWidth:node.scrollWidth,clientWidth:node.clientWidth}));
 expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
 await page.getByRole('slider',{name:/Zeilenhöhe/}).fill('0');
 await page.locator('.family-timeline-lane-picker summary').click();
 await page.getByLabel('Leere ausblenden').check();
 await expect(page.locator('.family-timeline-lane[data-lane-id="member-3"]')).toHaveCount(0);
 await expectNoHorizontalPageOverflow(page);
 await page.locator('.family-timeline-lane-picker summary').click();
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
