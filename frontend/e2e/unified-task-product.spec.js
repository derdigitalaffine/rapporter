import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';

async function setup(page){
 await installApiMocks(page);
 const state={creates:[],captures:[],requests:[],actions:[{id:'task:undated',family:'family-1',kind:'task',title:'Ohne Termin sichtbar',state:'open',context:{},primary_action:{id:'complete',method:'POST',href:'/api/tasks/undated/toggle/'},allowed_actions:[],deep_link:'/?page=tasks&task=undated'}]};
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname;let body={};try{body=req.postDataJSON()||{}}catch{}
  if(path==='/api/actions/'&&req.method()==='GET'){state.requests.push(url.searchParams.get('scope'));return route.fulfill({json:{actions:state.actions,focus:[],next:null}})}
  if(path==='/api/tasks/'&&req.method()==='POST'){state.creates.push(body);const task={...body,id:'created-task',family:'family-1'};state.actions.push({id:'task:created-task',family:'family-1',kind:'task',title:body.title,state:'open',schedule:body.action_schedule,context:{},primary_action:{id:'complete',method:'POST',href:'/api/tasks/created-task/toggle/'},allowed_actions:[],deep_link:'/?page=tasks&task=created-task'});return route.fulfill({status:201,json:task})}
  if(path==='/api/actions/capture/'&&req.method()==='GET')return route.fulfill({json:{suggestions:[],suggestions_enabled:true,icon_suggestions:['tasks']}});
  if(path==='/api/actions/capture/'&&req.method()==='POST'){state.captures.push(body);return route.fulfill({status:201,json:{id:'completion-1',action_id:'task:captured-task'}})}
  return route.fallback();
 });
 await page.goto('/?page=todo');
 await expect(page.getByText('Ohne Termin sichtbar',{exact:true})).toBeVisible();
 return state;
}

test('normal dialog writes a scheduled task once through the canonical task contract',async({page})=>{
 const state=await setup(page);
 await page.locator('.todo-workspace-actions').getByRole('button',{name:'Aufgabe hinzufügen',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByRole('textbox',{name:'Titel',exact:true}).fill('Gemeinsames Objekt');
 await dialog.getByText('Wiederholung & Planung',{exact:true}).click();
 await dialog.getByLabel('Wiederholung',{exact:true}).selectOption('weekly');
 await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(dialog).toHaveCount(0);
 expect(state.creates).toHaveLength(1);
 expect(state.creates[0].action_schedule.recurrence.frequency).toBe('weekly');
 expect(state.captures).toHaveLength(0);
 await expect(page.getByText('Gemeinsames Objekt',{exact:true})).toBeVisible();
});

test('retrospective path explicitly creates the same task kind, never a new routine',async({page})=>{
 const state=await setup(page);
 await page.getByRole('button',{name:'Ich habe gerade …',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByRole('textbox',{name:'Ich habe gerade …',exact:true}).fill('Schon erledigte Aufgabe');
 await dialog.getByRole('button',{name:'Neu anlegen und jetzt erledigen'}).click();
 await expect(dialog.getByText('Erledigt gespeichert.')).toBeVisible();
 expect(state.captures).toHaveLength(1);
 expect(state.captures[0]).toMatchObject({create_new:true,create_kind:'task',title:'Schon erledigte Aufgabe'});
 expect(state.creates).toHaveLength(0);
});

test('closing a dirty dialog preserves text until explicit discard',async({page})=>{
 await setup(page);
 await page.locator('.todo-workspace-actions').getByRole('button',{name:'Aufgabe hinzufügen',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByRole('textbox',{name:'Titel',exact:true}).fill('Entwurf bleibt');
 await dialog.getByRole('button',{name:'Schließen',exact:true}).click();
 const confirm=page.getByRole('alertdialog');
 await expect(confirm).toBeVisible();
 await confirm.getByRole('button',{name:'Abbrechen',exact:true}).click();
 await expect(dialog.getByRole('textbox',{name:'Titel',exact:true})).toHaveValue('Entwurf bleibt');
});

test('workspace search and browser back retain a single task surface',async({page})=>{
 await setup(page);
 await page.getByRole('searchbox',{name:'Aufgaben durchsuchen'}).fill('nicht vorhanden');
 await expect(page.getByText('Keine passenden Aufgaben.')).toBeVisible();
 await page.getByRole('searchbox',{name:'Aufgaben durchsuchen'}).clear();
 const tabs=page.getByRole('navigation',{name:'Aufgaben',exact:true});
 await tabs.getByRole('button',{name:'Heute',exact:true}).click();
 await expect(page).toHaveURL(/todo=today/);
 await tabs.getByRole('button',{name:'Alle',exact:true}).click();
 await page.goBack();
 await expect(tabs.getByRole('button',{name:'Heute',exact:true})).toHaveAttribute('aria-current','page');
});

test('cyclic action pagination stops with an error rather than an endless read',async({page})=>{
 await installApiMocks(page);
 let requests=0;
 await page.route('**/api/actions/?**',route=>{requests++;return route.fulfill({json:{results:[],next:'/api/actions/?family=family-1&scope=all&cursor=loop'}})});
 await page.goto('/?page=todo');
 await expect(page.getByRole('alert')).toContainText('To-dos konnten nicht geladen werden.');
 expect(requests).toBe(2);
});

test('legacy task deep link opens the same editor inside the unified workspace',async({page})=>{
 await installApiMocks(page);
 await page.goto('/?page=tasks&task=task-1');
 await expect(page.getByRole('dialog').getByRole('textbox',{name:'Titel',exact:true})).toHaveValue('Wäsche aufhängen');
 await expect(page.getByRole('dialog',{includeHidden:true})).toHaveCount(1);
 await page.getByRole('dialog').getByRole('button',{name:'Schließen',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page).not.toHaveURL(/task=/);
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Aufgaben',exact:true})).toHaveAttribute('aria-current','page');
});

for(const width of [320,390,1024,1440])test(`task dialog and workspace fit ${width}px with reachable touch targets`,async({page},info)=>{
 await page.setViewportSize({width,height:width===320?568:900});
 await setup(page);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('.todo-workspace-actions').getByRole('button',{name:'Aufgabe hinzufügen',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByRole('textbox',{name:'Titel',exact:true}).fill('Eine sehr lange deutsche Aufgabe mit vielen hilfreichen Details');
 await dialog.getByRole('button',{name:'Speichern',exact:true}).scrollIntoViewIfNeeded();
 const button=await dialog.getByRole('button',{name:'Speichern',exact:true}).boundingBox();
 expect(button.height).toBeGreaterThanOrEqual(44);expect(button.y+button.height).toBeLessThanOrEqual(width===320?568:900);
 expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 const axe=await new AxeBuilder({page}).include('[data-family-overlay-owner="base-ui"][role="dialog"]').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
 expect(axe.violations.filter(v=>['serious','critical'].includes(v.impact))).toEqual([]);
 await page.screenshot({path:info.outputPath(`unified-task-${width}.png`)});
});
