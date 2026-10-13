import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,{language='de',viewport}={}){
 if(viewport)await page.setViewportSize(viewport);
 await installApiMocks(page,{language});
 let layout={
  version:2,
  revision:2,
  widgets:[
   {id:'weather',visible:true,size:'medium'},
   {id:'priority',visible:true,size:'wide'},
   {id:'future-private',visible:true,size:'medium'},
   {id:'pinboard',visible:false,size:'compact'},
   {id:'shopping',visible:false,size:'compact'},
  ],
 };
 await page.route('**/api/today-layout/**',async route=>{
  if(route.request().method()==='PUT')layout={...route.request().postDataJSON(),revision:layout.revision+1};
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(layout)});
 });
 await page.goto('/');
 const edit=page.getByRole('button',{name:language==='de'?'Anpassen':'Customize'});
 await expect(edit).toBeEnabled();
 return {getLayout:()=>layout};
}

test('library separates placed widgets from registry-backed additions and preserves unavailable rows',async({page})=>{
 const {getLayout}=await boot(page);
 await expect(page.locator('[data-today-widget="games"]')).toHaveCount(0);
 await page.getByRole('button',{name:'Anpassen'}).click();
 const editor=page.getByRole('region',{name:'Anpassen'});
 await expect(editor.getByRole('heading',{name:'Dein Heute'})).toBeVisible();
 await expect(editor.getByRole('heading',{name:'Widgets hinzufügen'})).toBeVisible();
 await expect(editor.locator('[data-editor-widget-id="weather"]')).toBeVisible();
 await expect(editor.locator('[data-editor-widget-id="focus"]')).toBeVisible();
 await expect(editor.locator('[data-editor-widget-id="priority"]')).toHaveCount(0);
 await expect(editor.locator('[data-editor-widget-id="future-private"]')).toHaveCount(0);
 await expect(editor.locator('[data-library-widget="future-private"]')).toHaveCount(0);
 await expect(editor.locator('[data-library-widget="games"]')).toBeVisible();
 const pinboardCard=editor.locator('[data-library-widget="pinboard"]');
 await expect(pinboardCard).toBeVisible();
 await expect(pinboardCard.getByRole('img',{name:'Illustrative Vorschau ohne Live-Daten'})).toBeVisible();
 await pinboardCard.getByRole('button',{name:'Hinzufügen'}).click();
 const pinboardRow=editor.locator('[data-editor-widget-id="pinboard"]');
 await expect(pinboardRow).toBeVisible();
 await expect(pinboardCard).toHaveCount(0);
 const size=pinboardRow.getByRole('combobox',{name:'Pinnwand · Größe'});
 await expect(size.locator('option')).toHaveText(['Kompakt','Mittel','Breit']);
 await pinboardRow.getByRole('button',{name:'Ausblenden'}).click();
 const returnedCard=editor.locator('[data-library-widget="pinboard"]');
 await expect(returnedCard).toBeVisible();
 await expect(returnedCard.getByRole('button',{name:'Hinzufügen'})).toBeFocused();
 await returnedCard.getByRole('button',{name:'Hinzufügen'}).click();
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(editor).toHaveCount(0);
 const saved=getLayout();
 expect(saved.version).toBe(2);
 expect(saved.widgets.find(row=>row.id==='focus')?.visible).toBe(true);
 expect(saved.widgets.some(row=>row.id==='priority')).toBe(false);
 expect(saved.widgets.find(row=>row.id==='pinboard')?.visible).toBe(true);
 expect(saved.widgets.find(row=>row.id==='games')?.visible).toBe(false);
 expect(saved.widgets.find(row=>row.id==='future-private')).toEqual({id:'future-private',visible:true,size:'medium'});
});

test('library categories and size metadata are localized without live preview content',async({page})=>{
 await boot(page,{language:'en'});
 await page.getByRole('button',{name:'Customize'}).click();
 const editor=page.getByRole('region',{name:'Customize'});
 await expect(editor.getByRole('heading',{name:'Add widgets'})).toBeVisible();
 await expect(editor.getByRole('heading',{name:'Now & planning'})).toBeVisible();
 await expect(editor.getByRole('heading',{name:'Family & communication'})).toBeVisible();
 await expect(editor.getByRole('heading',{name:'Household'})).toBeVisible();
 const shopping=editor.locator('[data-library-widget="shopping"]');
 await expect(shopping).toContainText('Keep open shopping items close at hand.');
 await expect(shopping.getByLabel('Supported sizes')).toContainText('Compact');
 await expect(shopping.getByLabel('Supported sizes')).toContainText('Wide');
 await expect(shopping).not.toContainText('Milch');
});

for(const viewport of [{width:320,height:720},{width:390,height:844}]){
 test(`widget library stays single-column and overflow-free at ${viewport.width}px`,async({page})=>{
  await boot(page,{viewport});
  await page.getByRole('button',{name:'Anpassen'}).click();
  const editor=page.getByRole('region',{name:'Anpassen'});
  await expect(editor).toBeVisible();
  expect(await editor.evaluate(element=>element.scrollWidth<=element.clientWidth+1)).toBe(true);
  const cards=editor.locator('.today-widget-library-card');
  expect(await cards.count()).toBeGreaterThan(0);
  const columns=await editor.locator('.today-widget-library-grid').first().evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').length);
  expect(columns).toBe(1);
  const touchTargets=await editor.locator('.today-widget-library-card>button').evaluateAll(buttons=>buttons.every(button=>button.getBoundingClientRect().height>=44));
  expect(touchTargets).toBe(true);
 });
}
