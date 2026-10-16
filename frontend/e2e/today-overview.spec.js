import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';
import {defaultTodayWidgets} from '../src/todayWidgetRegistry.js';

const now='2026-10-10T10:00:00.000Z';
async function boot(page,{saved=false,failed=false,badNext=false}={}){
 await page.addInitScript(value=>{const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[value]))}static now(){return new RealDate(value).getTime()}}},now);
 const state=await installApiMocks(page);
 const requests=[];
 if(!saved)state.todayLayout={version:2,revision:0,widgets:defaultTodayWidgets()};
 state.events=[{id:'event-today',family:'family-1',type:'calendar.event',title:'Kinderarzt',starts_at:'2026-10-10T14:00:00Z',ends_at:'2026-10-10T15:00:00Z',payload:{}}];
 await page.route('**/api/**',route=>{
  const url=new URL(route.request().url());requests.push(url.pathname+url.search);
  if(url.pathname==='/api/dashboard/')return route.fulfill({json:{family:'family-1',tasks:state.tasks,task_lists:state.taskLists,events:state.events,routines:[],shopping_lists:state.shoppingLists,overview:{shopping_open_count:12,pin_count:4}}});
  if(url.pathname==='/api/chat/conversations/')return failed?route.fulfill({status:503,json:{detail:'unavailable'}}):route.fulfill({json:{results:[{id:'chat',unread:3}]}});
  if(url.pathname==='/api/actions/'){
   if(failed)return route.fulfill({status:503,json:{detail:'unavailable'}});
   const second=url.searchParams.has('cursor');
   const row={id:second?'task:two':'task:one',family:'family-1',kind:'task',title:second?'Zweiter Punkt':'Erster Punkt',state:second?'due':'overdue',urgency:'high',ranking:{bucket:1},context:{},allowed_actions:[],deep_link:'/?page=todo'};
   return route.fulfill({json:{results:[row],next:second?null:`/api/actions/?family=${badNext?'foreign':'family-1'}&scope=today&cursor=two`}});
  }
  return route.fallback();
 });
 await page.goto('/');
 await expect(page.getByTestId('today-layout-edit')).toBeEnabled();
 return {state,requests};
}

test('fresh Today has compact greeting, genuine full counts and canonical direct links',async({page})=>{
 const {requests}=await boot(page);
 const overview=page.getByTestId('today-overview');
 await expect(overview.getByRole('link',{name:/2 Aufgaben/})).toBeVisible();
 await expect(overview.getByRole('link',{name:/12 Einkauf/})).toBeVisible();
 await expect(overview.getByRole('link',{name:/4 Pinnwand/})).toBeVisible();
 await expect(overview.getByRole('link',{name:/3 Nachrichten/})).toBeVisible();
 await expect(overview.getByRole('link',{name:/1 Kalender/})).toBeVisible();
 await expect(page.locator('main').getByRole('heading',{level:1})).toHaveText('Guten Tag, Alex!');
 await expect(page.locator('.today-week')).toHaveCount(0);
 await expect(page.getByTestId('today-timeline')).toHaveCount(0);
 await expect(page.getByTestId('today-todos')).toHaveCount(0);
 await expect(page.getByTestId('today-focus').getByRole('heading',{name:'Wichtig',exact:true})).toBeVisible();
 expect(requests.filter(path=>path.startsWith('/actions/'))).toHaveLength(0);
 expect(requests.filter(path=>path.startsWith('/api/actions/'))).toHaveLength(2);
 expect(requests.filter(path=>path.startsWith('/api/loyalty-cards/'))).toHaveLength(0);
 expect(requests.filter(path=>path.startsWith('/api/auth/session/')).length).toBe(1);
 await overview.getByRole('link',{name:/2 Aufgaben/}).click();
 await expect(page).toHaveURL(/page=todo.*todo=today/);
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Aufgaben',exact:true})).toHaveAttribute('aria-current','page');
});

test('unavailable sources are not reported as zero and do not block other tiles',async({page})=>{
 await boot(page,{failed:true});
 const overview=page.getByTestId('today-overview');
 await expect(overview.locator('[data-domain="todo"]')).toContainText('Nicht verfügbar');
 await expect(overview.locator('[data-domain="inbox"]')).toContainText('Nicht verfügbar');
 await expect(overview.locator('[data-domain="todo"] .today-overview-value')).toHaveText('—');
 await expect(overview.locator('[data-domain="shopping"] .today-overview-value')).toHaveText('12');
});

test('cross-family pagination fails closed without fetching the foreign selector',async({page})=>{
 const {requests}=await boot(page,{badNext:true});
 await expect(page.getByTestId('today-overview').locator('[data-domain="todo"]')).toContainText('Nicht verfügbar');
 expect(requests.some(path=>path.includes('family=foreign'))).toBe(false);
});

test('saved layouts stay personal; reset is previewed and cancellable before explicit save',async({page})=>{
 const {state}=await boot(page,{saved:true});
 await expect(page.getByTestId('today-overview')).toHaveCount(0);
 await expect(page.getByTestId('today-timeline')).toBeVisible();
 const before=JSON.stringify(state.todayLayout);
 await page.getByTestId('today-layout-edit').click();
 const editor=page.getByRole('region',{name:'Anpassen',exact:true});
 await editor.getByRole('button',{name:'Standard wiederherstellen',exact:true}).click();
 await expect(page.getByTestId('today-overview')).toBeVisible();
 await editor.getByRole('button',{name:'Abbrechen',exact:true}).click();
 await expect(page.getByTestId('today-overview')).toHaveCount(0);
 expect(JSON.stringify(state.todayLayout)).toBe(before);
 await page.getByTestId('today-layout-edit').click();
 await editor.getByRole('button',{name:'Standard wiederherstellen',exact:true}).click();
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(page.getByTestId('today-overview')).toBeVisible();
 expect(state.todayLayout.widgets.filter(row=>row.visible).map(row=>row.id)).toEqual(['situation','overview','focus']);
});

for(const width of [320,390,1024,1440])test(`overview is touch and keyboard reachable without overflow at ${width}px`,async({page},info)=>{
 await page.setViewportSize({width,height:width===320?568:900});
 await page.emulateMedia({reducedMotion:'reduce'});
 await boot(page);
 const overview=page.getByTestId('today-overview');
 await expect(overview.locator('[data-domain="todo"] .today-overview-value')).toHaveText('2');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 for(const tile of await overview.getByRole('link').all()){
  const box=await tile.boundingBox();expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44);
 }
 await overview.locator('[data-domain="todo"]').focus();
 await page.keyboard.press('Tab');
 await expect(overview.locator('[data-domain="calendar"]')).toBeFocused();
 expect((await new AxeBuilder({page}).include('[data-testid="today-overview"]').analyze()).violations).toEqual([]);
 await page.screenshot({path:info.outputPath(`today-overview-${width}.png`),fullPage:true});
});
