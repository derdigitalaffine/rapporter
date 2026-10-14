import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
import AxeBuilder from '@axe-core/playwright';

async function boot(page){
 await installApiMocks(page);
 await page.route('**/api/scheduling/preview/**',async route=>{
  const body=route.request().postDataJSON()||{};
  const recurrence=body.text?{frequency:'quarterly',interval:1,nth_weekdays:[{weekday:'MO',ordinal:1}]}:body.rule?.recurrence;
  const anchor=body.anchor_date||body.rule?.anchor_date||'2026-01-01';
  return route.fulfill({json:{rule:{version:'scheduling-rule-v1',timezone:'Europe/Berlin',time_mode:'wall_clock',anchor_date:anchor,recurrence},summary:'Jedes Quartal · erster Montag',occurrences:['2026-01-05','2026-04-06','2026-07-06','2026-10-05','2027-01-04'],timezone:'Europe/Berlin'}});
 });
 const requests=[];let done=false;let dependencies=[];const item={id:'task:task-1',family:'family-1',kind:'task',title:'Müll rausbringen',state:'due',urgency:'normal',assignee:null,icon:'waste',context:{},primary_action:{id:'complete',method:'POST',href:'/api/tasks/task-1/toggle/'},allowed_actions:[{id:'complete',method:'POST',href:'/api/tasks/task-1/toggle/'},{id:'edit',method:'PATCH',href:'/api/tasks/task-1/'}],completion_command:{href:'/api/actions/execute/',version:'action-completion-v1'}};
 await page.route('**/api/scheduling/dependencies/**',async route=>{const req=route.request();const url=new URL(req.url());const body=req.postDataJSON()||{};
  if(url.pathname==='/api/scheduling/dependencies/preview/'&&req.method()==='POST')return route.fulfill({json:{summary:'3 Tage vorher',occurrences:[{anchor_occurrence_key:'2026-11-02',anchor_at:'2026-11-02T09:00:00+01:00',scheduled_for:'2026-10-30T09:00:00+01:00'},{anchor_occurrence_key:'2026-11-09',anchor_at:'2026-11-09T09:00:00+01:00',scheduled_for:'2026-11-06T09:00:00+01:00'}]}});
  if(url.pathname==='/api/scheduling/dependencies/'&&req.method()==='GET')return route.fulfill({json:{dependencies,origins:[]}});
  if(url.pathname==='/api/scheduling/dependencies/'&&req.method()==='POST'){requests.push({dependency:body});const row={id:'dep-1',...body,relative_summary:'3 Tage vorher',enabled:true,materializations:[{id:'mat-1',status:'materialized',scheduled_for:'2026-10-30T09:00:00+01:00'}]};dependencies=[row];return route.fulfill({status:201,json:row})}
  return route.fallback();
 });
 await page.route('**/api/actions/**',async route=>{const req=route.request();const url=new URL(req.url());const body=req.postDataJSON()||{};
  if(url.pathname==='/api/actions/'&&req.method()==='GET')return route.fulfill({json:{actions:done?[]:[item],focus:[],preferences:{smart_ranking_enabled:true,today_sort:'smart'}}});
  if(url.pathname==='/api/actions/capture/'&&req.method()==='GET')return route.fulfill({json:{suggestions:done?[]:[item],icon_suggestions:['waste','recycle','tasks'],suggestions_enabled:true}});
  if(url.pathname==='/api/actions/capture/'&&req.method()==='POST'){requests.push(body);done=true;return route.fulfill({json:{id:'completion-1',action_id:body.action_id||'routine:created',actor:1,duration_minutes:body.duration_minutes}})}
  if(url.pathname==='/api/actions/execute/'){requests.push(body);done=body.operation==='complete';return route.fulfill({json:{id:'completion-1',actor:1}})}
  if(url.pathname==='/api/actions/task/task-1/'&&req.method()==='GET')return route.fulfill({json:{id:'action-1',icon:'waste',accent_token:'',icon_suggestions:['waste','recycle','tasks'],icon_choices:['waste','recycle','tasks'],accent_choices:['','blue'],schedule:{},prediction:null}});
  if(url.pathname==='/api/actions/task/task-1/'&&req.method()==='PATCH'){requests.push(body);return route.fulfill({json:body})}
  return route.fallback();
 });
 await page.goto('/?page=todo');await page.waitForLoadState('networkidle');return requests;
}

test('capture chooses existing action explicitly with duration and undo',async({page})=>{
 const requests=await boot(page);const capture=page.getByRole('region',{name:'Ich habe gerade …'});
 await capture.getByLabel('Ich habe gerade …',{exact:true}).fill('Müll rausgebracht');
 await capture.getByText('Dauer und Vorschläge',{exact:true}).click();await capture.getByLabel('Dauer (optional)').selectOption('10');
 await capture.getByRole('button',{name:'Müll rausbringen',exact:true}).click();
 await expect.poll(()=>requests.at(-1)?.action_id).toBe('task:task-1');expect(requests.at(-1).duration_minutes).toBe(10);
 await capture.getByRole('button',{name:'Rückgängig',exact:true}).click();
 await expect.poll(()=>requests.at(-1)?.operation).toBe('undo');expect(requests.at(-1).completion_id).toBe('completion-1');
});

test('new capture requires explicit create and retains original title',async({page})=>{
 const requests=await boot(page);const capture=page.getByRole('region',{name:'Ich habe gerade …'});
 await capture.getByLabel('Ich habe gerade …',{exact:true}).fill('Betten gemacht');
 await capture.getByRole('button',{name:'Neu anlegen und jetzt erledigen'}).click();
 await expect.poll(()=>requests.at(-1)?.create_new).toBe(true);expect(requests.at(-1).title).toBe('Betten gemacht');expect(requests.at(-1).request_id).toMatch(/^[0-9a-f-]{36}$/);
});

test('schedule editor shares server-authoritative recurrence UX with calendar events',async({page})=>{
 const requests=await boot(page);const row=page.locator('[data-action-id="task:task-1"]');
 await row.getByLabel('Schnellaktionen: Müll rausbringen').click();await row.getByRole('button',{name:'Zeitplan & Darstellung'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByLabel('Planungsmodus')).not.toBeVisible();
 await dialog.getByText('Mehr Optionen',{exact:true}).click();
 await expect(dialog.getByLabel('Planungsmodus')).toBeVisible();
 await dialog.getByLabel('In eigenen Worten',{exact:true}).fill('immer am ersten Montag im Quartal');
 await dialog.getByRole('button',{name:'Erkennen',exact:true}).click();
 await expect(dialog.getByText(/erster Montag/)).toBeVisible();
 await expect(dialog.getByLabel('Wiederholung',{exact:true})).toHaveValue('quarterly');
 await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect.poll(()=>requests.at(-1)?.schedule?.recurrence?.frequency).toBe('quarterly');
 expect(requests.at(-1).schedule.recurrence.nth_weekdays).toEqual([{weekday:'MO',ordinal:1}]);
});

test('lead and follow-up editor previews and creates a canonical dependency',async({page})=>{
 const requests=await boot(page);const row=page.locator('[data-action-id="task:task-1"]');
 await row.getByLabel('Schnellaktionen: Müll rausbringen').click();await row.getByRole('button',{name:'Zeitplan & Darstellung'}).click();
 const dialog=page.getByRole('dialog');await expect(dialog.getByText('Vor- & Nachgänge',{exact:true})).toBeVisible();
 await dialog.getByRole('button',{name:'3 Tage vorher',exact:true}).click();
 await dialog.getByRole('textbox',{name:'Titel',exact:true}).fill('Tonnen rausstellen');
 await expect(dialog.getByText(/30\.10\./)).toBeVisible();
 await dialog.getByRole('button',{name:'Regel speichern',exact:true}).click();
 await expect.poll(()=>requests.find(entry=>entry.dependency)?.dependency?.anchor_id).toBe('action-1');
 const body=requests.find(entry=>entry.dependency).dependency;expect(body.anchor_type).toBe('action');expect(body.output_type).toBe('calendar.event');expect(body.relative_rule.offset).toEqual({value:3,unit:'days'});
 await expect(dialog.getByText('Tonnen rausstellen',{exact:true})).toBeVisible();
});

for(const width of [320,390,1024,1440])test(`capture and action rows fit ${width}px and remain accessible`,async({page})=>{
 await page.setViewportSize({width,height:900});await boot(page);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 const box=await page.getByRole('button',{name:'Erledigen: Müll rausbringen'}).boundingBox();expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44);
 const result=await new AxeBuilder({page}).include('main').withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();expect(result.violations.filter(v=>['critical','serious'].includes(v.impact))).toEqual([]);
});