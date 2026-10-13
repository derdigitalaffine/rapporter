import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
import AxeBuilder from '@axe-core/playwright';

async function boot(page){
 await installApiMocks(page);
 const requests=[];let done=false;const item={id:'task:task-1',family:'family-1',kind:'task',title:'Müll rausbringen',state:'due',urgency:'normal',assignee:null,icon:'waste',context:{},primary_action:{id:'complete',method:'POST',href:'/api/tasks/task-1/toggle/'},allowed_actions:[{id:'complete',method:'POST',href:'/api/tasks/task-1/toggle/'},{id:'edit',method:'PATCH',href:'/api/tasks/task-1/'}],completion_command:{href:'/api/actions/execute/',version:'action-completion-v1'}};
 await page.route('**/api/actions/**',async route=>{const req=route.request();const url=new URL(req.url());const body=req.postDataJSON()||{};
  if(url.pathname==='/api/actions/'&&req.method()==='GET')return route.fulfill({json:{actions:done?[]:[item],focus:[],preferences:{smart_ranking_enabled:true,today_sort:'smart'}}});
  if(url.pathname==='/api/actions/capture/'&&req.method()==='GET')return route.fulfill({json:{suggestions:done?[]:[item],icon_suggestions:['waste','recycle','tasks'],suggestions_enabled:true}});
  if(url.pathname==='/api/actions/capture/'&&req.method()==='POST'){requests.push(body);done=true;return route.fulfill({json:{id:'completion-1',action_id:body.action_id||'routine:created',actor:1,duration_minutes:body.duration_minutes}})}
  if(url.pathname==='/api/actions/execute/'){requests.push(body);done=body.operation==='complete';return route.fulfill({json:{id:'completion-1',actor:1}})}
  if(url.pathname==='/api/actions/task/task-1/'&&req.method()==='GET')return route.fulfill({json:{icon:'waste',accent_token:'',icon_suggestions:['waste','recycle','tasks'],icon_choices:['waste','recycle','tasks'],accent_choices:['','blue'],schedule:{},prediction:null}});
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

test('schedule editor uses progressive fields and a versioned contract',async({page})=>{
 const requests=await boot(page);const row=page.locator('[data-action-id="task:task-1"]');
 await row.getByLabel('Schnellaktionen: Müll rausbringen').click();await row.getByRole('button',{name:'Zeitplan & Darstellung'}).click();
 const dialog=page.getByRole('dialog');await dialog.getByLabel('Wann?',{exact:true}).fill('jeden Montag um 18:00');
 await expect(dialog.getByLabel('Planungsmodus')).not.toBeVisible();await dialog.getByText('Mehr Optionen',{exact:true}).click();await expect(dialog.getByLabel('Planungsmodus')).toBeVisible();
 await dialog.getByRole('button',{name:'Speichern',exact:true}).click();await expect.poll(()=>requests.at(-1)?.schedule_text).toBe('jeden Montag um 18:00');
});

for(const width of [320,390,1024,1440])test(`capture and action rows fit ${width}px and remain accessible`,async({page})=>{
 await page.setViewportSize({width,height:900});await boot(page);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 const box=await page.getByRole('button',{name:'Erledigen: Müll rausbringen'}).boundingBox();expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44);
 const result=await new AxeBuilder({page}).include('main').withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();expect(result.violations.filter(v=>['critical','serious'].includes(v.impact))).toEqual([]);
});
