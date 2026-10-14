import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const directEventProfile={
  ranking_version:1,
  cold_start_threshold:5,
  preferences:{smart_ranking_enabled:true,context_ranking_enabled:true,time_patterns_enabled:false,direct_mode:true,direct_action_id:'event',max_quick_actions:4,pinned_action_ids:[],hidden_action_ids:[],manual_order:[],learning_scope:'family'},
  stats:[],
};

async function routeDirectEventCreate(page){
  await page.route('**/api/create-actions/**',async route=>{
    if(route.request().method()==='POST')return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({...directEventProfile,accepted:true,deduplicated:false})});
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(directEventProfile)});
  });
}

async function openNewEventEditor(page){
  const fab=page.locator('.global-create-fab');
  await expect(fab).toHaveAttribute('aria-label','Termin hinzufügen');
  await fab.click();
  const dialog=page.getByRole('dialog',{name:'Termin hinzufügen'});
  await expect(dialog).toBeVisible();
  return dialog;
}

function minutesBetween(start,end){return (new Date(end)-new Date(start))/60000}
function localInputValue(value){const date=new Date(value);return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)}

test('new event editor is touch-first, defaults to me and saves start plus duration canonically',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await routeDirectEventCreate(page);
  let created=null;
  await page.route('**/api/events/',async route=>{
    if(route.request().method()!=='POST')return route.fallback();
    created=route.request().postDataJSON();
    return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id:'event-created',...created})});
  });
  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');

  const dialog=await openNewEventEditor(page);
  await expect(dialog.getByRole('radio',{name:/Start \+ Dauer/})).toBeChecked();
  await expect(dialog.getByLabel('Andere Dauer')).toHaveValue('60');

  const alex=dialog.getByRole('checkbox',{name:/Alex/});
  const sam=dialog.getByRole('checkbox',{name:/Sam/});
  await expect(alex).toBeChecked();
  await expect(sam).not.toBeChecked();

  await dialog.getByRole('button',{name:'Alle',exact:true}).click();
  await expect(alex).toBeChecked();
  await expect(sam).toBeChecked();
  const familyEvent=dialog.getByRole('checkbox',{name:/Familientermin/});
  await familyEvent.check();
  await dialog.getByRole('button',{name:'Niemand',exact:true}).click();
  await expect(alex).not.toBeChecked();
  await expect(sam).not.toBeChecked();
  await expect(familyEvent).toBeChecked();
  await dialog.getByRole('button',{name:'Nur ich',exact:true}).click();
  await expect(alex).toBeChecked();
  await expect(sam).not.toBeChecked();

  await dialog.getByRole('radio',{name:/Start \+ Endzeit/}).check();
  await dialog.getByLabel('Beginn').fill('2026-10-15T10:00');
  await dialog.getByLabel('Ende').fill('2026-10-15T11:45');
  await dialog.getByRole('radio',{name:/Start \+ Dauer/}).check();
  await expect(dialog.getByLabel('Andere Dauer')).toHaveValue('105');
  await dialog.getByRole('radio',{name:/Start \+ Endzeit/}).check();
  await expect(dialog.getByLabel('Ende')).toHaveValue('2026-10-15T11:45');
  await dialog.getByRole('radio',{name:/Start \+ Dauer/}).check();
  await dialog.getByRole('button',{name:'1.5 Std.',exact:true}).click();
  await expect(dialog.getByLabel('Andere Dauer')).toHaveValue('90');

  const participantBox=await dialog.locator('.event-editor-participant-card').first().boundingBox();
  const durationBox=await dialog.getByRole('button',{name:'1.5 Std.',exact:true}).boundingBox();
  expect(participantBox?.height||0).toBeGreaterThanOrEqual(44);
  expect(durationBox?.height||0).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);

  await dialog.getByLabel('Titel').fill('Physio');
  await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
  await expect.poll(()=>created).not.toBeNull();
  expect(created.participants).toEqual(['member-1']);
  expect(created.is_family_event).toBe(true);
  expect(minutesBetween(created.starts_at,created.ends_at)).toBe(90);
  expect(created.payload.provider).toBe('FamilyOS');
});

test('new event editor saves first Monday of each calendar quarter',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await routeDirectEventCreate(page);
  let created=null;
  await page.route('**/api/events/',async route=>{
    if(route.request().method()!=='POST')return route.fallback();
    created=route.request().postDataJSON();
    return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id:'event-created',...created})});
  });
  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');

  const dialog=await openNewEventEditor(page);
  await dialog.getByLabel('Titel').fill('Quartalsplanung');
  await dialog.getByRole('button',{name:'Weitere Details'}).click();
  await dialog.getByLabel('Wiederholung').selectOption('quarterly');
  await dialog.getByLabel('Wochentag im Quartal').selectOption('MO');
  await dialog.getByLabel('Welche Position?').selectOption('1');
  await dialog.getByRole('button',{name:'Speichern',exact:true}).click();

  await expect.poll(()=>created).not.toBeNull();
  expect(created.payload.recurrence).toEqual({frequency:'quarterly',interval:1,nth_weekdays:[{weekday:'MO',ordinal:1}]});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
});

test('editing an existing multi-person event keeps participants, family marker and end-time mode',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const state=await installApiMocks(page,{dismissOnboarding:true});
  state.events[1]={...state.events[1],participants:['member-1','member-2'],is_family_event:true};
  await routeDirectEventCreate(page);
  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');

  await page.locator('.calendar-event-chip').filter({hasText:'Kinderarzt'}).first().click();
  const detail=page.getByRole('dialog').filter({hasText:'Kinderarzt'});
  await expect(detail).toBeVisible();
  await detail.getByRole('button',{name:'Termin bearbeiten',exact:true}).click();

  const dialog=page.getByRole('dialog',{name:'Termin bearbeiten'});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('radio',{name:/Start \+ Endzeit/})).toBeChecked();
  await expect(dialog.getByRole('checkbox',{name:/Alex/})).toBeChecked();
  await expect(dialog.getByRole('checkbox',{name:/Sam/})).toBeChecked();
  await expect(dialog.getByRole('checkbox',{name:/Familientermin/})).toBeChecked();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
});

test('editing a projected recurrence occurrence keeps the master series anchor',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const state=await installApiMocks(page,{dismissOnboarding:true});
  const occurrenceStart=new Date(Date.now()+5*3600000).toISOString();
  const occurrenceEnd=new Date(Date.now()+6*3600000).toISOString();
  const masterStart=new Date(Date.now()-48*3600000).toISOString();
  const masterEnd=new Date(Date.now()-47*3600000).toISOString();
  state.events[1]={
    ...state.events[1],
    title:'Serientermin',
    starts_at:occurrenceStart,
    ends_at:occurrenceEnd,
    recurrence_master_id:'event-1',
    recurrence_master_starts_at:masterStart,
    recurrence_master_ends_at:masterEnd,
    recurrence_occurrence_date:occurrenceStart.slice(0,10),
    payload:{...state.events[1].payload,recurrence:{frequency:'monthly',interval:1,nth_weekdays:[{weekday:'MO',ordinal:1}]}},
  };
  let patched=null;
  await page.route('**/api/events/event-1/',async route=>{
    if(route.request().method()!=='PATCH')return route.fallback();
    patched=route.request().postDataJSON();
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...state.events[1],...patched})});
  });
  await routeDirectEventCreate(page);
  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');

  await page.locator('.calendar-event-chip').filter({hasText:'Serientermin'}).first().click();
  const detail=page.getByRole('dialog').filter({hasText:'Serientermin'});
  await detail.getByRole('button',{name:'Termin bearbeiten',exact:true}).click();

  const dialog=page.getByRole('dialog',{name:'Termin bearbeiten'});
  await expect(dialog.getByLabel('Beginn')).toHaveValue(localInputValue(masterStart));
  await expect(dialog.getByLabel('Wiederholung')).toHaveValue('monthly');
  await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
  await expect.poll(()=>patched).not.toBeNull();
  expect(patched.starts_at).toBe(new Date(masterStart).toISOString());
  expect(patched.ends_at).toBe(new Date(masterEnd).toISOString());
  expect(patched.payload.recurrence).toEqual({frequency:'monthly',interval:1,nth_weekdays:[{weekday:'MO',ordinal:1}]});
});
