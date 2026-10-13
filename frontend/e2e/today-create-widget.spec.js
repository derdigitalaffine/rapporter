import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';
import {defaultTodayWidgets,normalizeTodayLayout} from '../src/todayWidgetRegistry.js';

async function setup(page,{language='de',role='owner',oldLayout=false,preferences={}}={}){
 const state=await installApiMocks(page,{language,dismissOnboarding:true});
 state.family.memberships[0].role=role;
 let layout={version:2,revision:4,widgets:defaultTodayWidgets()};
 if(oldLayout){layout.widgets=layout.widgets.filter(row=>row.id!=='quick-actions');layout.widgets.reverse()}
 const original=structuredClone(layout);const reads=[];const usages=[];
 await page.route('**/api/today-layout/**',route=>{
  if(route.request().method()==='PUT')layout={...route.request().postDataJSON(),revision:layout.revision+1};
  return route.fulfill({json:layout});
 });
 await page.route('**/api/create-actions/**',route=>{
  if(route.request().method()==='GET')reads.push(route.request().url());
  else usages.push(route.request().postDataJSON());
  return route.fulfill({json:{preferences,stats:[]}});
 });
 return {state,reads,usages,original,getLayout:()=>layout};
}
async function open(page){await page.goto('/');await expect(page.getByTestId('today-layout-edit')).toBeEnabled();await expect(page.locator('.global-create-fab')).toBeVisible()}
const widget=page=>page.getByTestId('today-quick-actions');
const ids=page=>widget(page).locator('[data-create-action]').evaluateAll(rows=>rows.map(row=>row.dataset.createAction));

test('fresh widget shares exact quickstart order and one ranking read with the palette',async({page})=>{
 const state=await setup(page,{preferences:{pinned_action_ids:['event'],hidden_action_ids:['task'],manual_order:['expense','shoppingItem']}});
 await open(page);await expect(widget(page).locator('button').first()).toContainText('Termin');
 expect(await ids(page)).toEqual(['event','expense','shoppingItem','contract']);
 expect(state.reads).toHaveLength(1);
 const order=await page.locator('[data-today-widget]').evaluateAll(rows=>rows.map(row=>row.dataset.todayWidget));
 expect(order.indexOf('quick-actions')).toBe(order.indexOf('todo')+1);expect(order.indexOf('pinboard')).toBe(order.indexOf('quick-actions')+1);
 await page.locator('.global-create-fab').click();
 expect(await page.locator('.create-action-card strong').allTextContents()).toEqual(await widget(page).locator('strong').allTextContents());
 await page.keyboard.press('Escape');expect(state.reads).toHaveLength(1);
});

test('one tap opens the canonical task editor and records only a successful save',async({page})=>{
 const state=await setup(page);await open(page);
 await widget(page).locator('[data-create-action="task"]').click();const dialog=page.getByRole('dialog');
 await expect(dialog.getByRole('heading',{name:'Aufgabe hinzufügen'})).toBeVisible();
 await expect(dialog.getByLabel('Titel')).toBeFocused();expect(state.usages).toEqual([]);
 await dialog.getByLabel('Titel').fill('Schnell von Heute');await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(dialog).toHaveCount(0);await expect.poll(()=>state.usages.length).toBe(1);
 expect(state.state.tasks.some(row=>row.title==='Schnell von Heute')).toBe(true);
 expect(state.usages[0].action_id).toBe('task');await expect(page).toHaveURL(/4173\/$/);
});

test('existing layouts add a hidden Library row without replacing saved choices',async({page})=>{
 const state=await setup(page,{oldLayout:true});await open(page);await expect(widget(page)).toHaveCount(0);
 await page.getByTestId('today-layout-edit').click();const editor=page.getByRole('region',{name:'Anpassen'});
 await editor.locator('[data-library-widget="quick-actions"]').getByRole('button',{name:'Hinzufügen',exact:true}).click();
 const row=editor.locator('[data-editor-widget-id="quick-actions"]');await expect(row).toBeVisible();
 await row.getByRole('combobox',{name:'Schnellaktionen · Größe'}).selectOption('wide');
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();await expect(widget(page)).toBeVisible();
 const saved=state.getLayout();expect(saved.widgets.find(row=>row.id==='quick-actions')).toEqual({id:'quick-actions',visible:true,size:'wide'});
 expect(saved.widgets.filter(row=>row.id!=='quick-actions')).toEqual(state.original.widgets);
});

test('stored preferences cannot expose role, module or premium-denied actions',async({page})=>{
 await setup(page,{role:'child',preferences:{pinned_action_ids:['wish','vehicle','baby','pets','message','event']}});await open(page);
 await expect(widget(page).locator('button').first()).toContainText('Termin');
 const actions=await ids(page);for(const id of ['wish','vehicle','baby','pets','message'])expect(actions).not.toContain(id);
});

test('family switch discards a delayed previous family ranking',async({page})=>{
 const state=await setup(page);
 const other={...state.state.family,id:'family-2',name:'Andere Familie',memberships:[{id:'member-other',user:1,role:'owner'}]};
 await page.route('**/api/families/**',route=>route.fulfill({json:[state.state.family,other]}));
 let release;const pending=new Promise(resolve=>release=resolve);
 await page.route('**/api/create-actions/**',async route=>{
  const family=new URL(route.request().url()).searchParams.get('family');
  if(family==='family-1')await pending;
  return route.fulfill({json:{preferences:{pinned_action_ids:[family==='family-1'?'expense':'shoppingItem']},stats:[]}});
 });
 await open(page);await page.locator('.family-switcher select').selectOption('family-2');
 await expect.poll(async()=>(await ids(page))[0]).toBe('shoppingItem');
 release();await expect.poll(async()=>(await ids(page))[0]).toBe('shoppingItem');
 await page.locator('.global-create-fab').click();await expect(page.locator('.create-action-card').first()).toContainText('Einkaufsartikel');
});

test('English widget is keyboard accessible and fits 320px at 200 percent',async({page})=>{
 await setup(page,{language:'en',preferences:{pinned_action_ids:['task']}});await open(page);
 await page.setViewportSize({width:320,height:844});await page.emulateMedia({reducedMotion:'reduce'});
 await widget(page).locator('button').first().focus();await page.keyboard.press('Enter');
 await expect(page.getByRole('dialog').getByRole('heading',{name:'Add task'})).toBeVisible();await page.keyboard.press('Escape');
 await page.locator('main').evaluate(el=>el.style.zoom='2');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('main').evaluate(el=>el.style.zoom='1');expect((await new AxeBuilder({page}).include('[data-testid="today-quick-actions"]').analyze()).violations).toEqual([]);
});

test('frontend compatibility adds quick actions hidden without resetting the old layout',async()=>{
 const old=defaultTodayWidgets().filter(row=>row.id!=='quick-actions').reverse();
 const result=normalizeTodayLayout({version:2,revision:9,widgets:old});
 expect(result.revision).toBe(9);expect(result.widgets.filter(row=>row.id!=='quick-actions')).toEqual(old);
 expect(result.widgets.find(row=>row.id==='quick-actions')).toEqual({id:'quick-actions',visible:false,size:'compact'});
});
