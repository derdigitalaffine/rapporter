import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const familyId='family-1';
const legacyIds=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes'];

function legacyLayout(){
 return {
  version:1,
  revision:0,
  widgets:legacyIds.map(id=>({
   id,
   visible:true,
   size:id==='weather'?'compact':id==='next'?'square':'full',
  })),
 };
}

async function boot(page,{width=1440,height=900}={}){
 await page.setViewportSize({width,height});
 await installApiMocks(page,{language:'de'});
 let layout=legacyLayout();
 await page.route('**/api/today-layout/**',async route=>{
  if(route.request().method()==='PUT'){
   layout={...route.request().postDataJSON(),revision:layout.revision+1};
  }
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(layout)});
 });
 await page.goto('/');
 await expect(page.getByRole('button',{name:'Anpassen'})).toBeEnabled();
 return {getLayout:()=>layout};
}

async function gridMetrics(page){
 return page.locator('.today-widget-grid').evaluate(grid=>{
  const rect=grid.getBoundingClientRect();
  const ratio=selector=>{
   const element=grid.querySelector(selector);
   if(!element)return null;
   return element.getBoundingClientRect().width/rect.width;
  };
  return {
   columns:getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length,
   flow:getComputedStyle(grid).gridAutoFlow,
   wide:ratio('[data-widget-size="wide"]'),
   compact:ratio('[data-widget-size="compact"]'),
   medium:ratio('[data-widget-size="medium"]'),
   order:[...grid.querySelectorAll('[data-today-widget]')].map(element=>element.dataset.todayWidget),
  };
 });
}

test('Today uses semantic desktop spans and keeps DOM order across breakpoints',async({page})=>{
 await boot(page);
 const desktop=await gridMetrics(page);
 expect(desktop.columns).toBe(12);
 expect(desktop.flow).toBe('row');
 expect(desktop.wide).toBeGreaterThan(.95);
 expect(desktop.compact).toBeGreaterThan(.28);
 expect(desktop.compact).toBeLessThan(.36);
 expect(desktop.medium).toBeGreaterThan(.45);
 expect(desktop.medium).toBeLessThan(.55);

 await page.setViewportSize({width:1024,height:768});
 const tablet=await gridMetrics(page);
 expect(tablet.columns).toBe(6);
 expect(tablet.flow).toBe('row');
 expect(tablet.compact).toBeGreaterThan(.45);
 expect(tablet.compact).toBeLessThan(.55);
 expect(tablet.medium).toBeGreaterThan(.45);
 expect(tablet.medium).toBeLessThan(.55);
 expect(tablet.order).toEqual(desktop.order);

 await page.setViewportSize({width:390,height:844});
 const phone=await gridMetrics(page);
 expect(phone.columns).toBe(1);
 expect(phone.flow).toBe('row');
 expect(phone.wide).toBeGreaterThan(.95);
 expect(phone.compact).toBeGreaterThan(.95);
 expect(phone.medium).toBeGreaterThan(.95);
 expect(phone.order).toEqual(desktop.order);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
});

test('reset defaults create a deliberate hierarchy and Today actions use canonical variants',async({page})=>{
 await boot(page,{width:1440,height:900});
 const edit=page.getByRole('button',{name:'Anpassen'});
 await expect(edit).toHaveClass(/secondary/);
 await edit.click();
 const editor=page.getByRole('region',{name:'Anpassen'});

 await editor.getByRole('button',{name:'Standard wiederherstellen'}).click();
 await expect(editor.getByRole('combobox',{name:'Wochenkompass · Größe'})).toHaveValue('wide');
 await expect(editor.getByRole('combobox',{name:'Reise · Größe'})).toHaveValue('medium');
 await expect(editor.getByRole('combobox',{name:'Pinnwand · Größe'})).toHaveValue('compact');
 await expect(editor.getByRole('combobox',{name:'Einkauf · Größe'})).toHaveValue('compact');
 await expect(editor.getByRole('combobox',{name:'Wetter · Größe'}).locator('option[value="medium"]')).toHaveText('Mittel');

 await expect(editor.getByRole('button',{name:'Standard wiederherstellen'})).toHaveClass(/ghost/);
 await expect(editor.getByRole('button',{name:'Abbrechen',exact:true})).toHaveClass(/secondary/);
 await expect(editor.getByRole('button',{name:'Speichern',exact:true})).toHaveClass(/primary/);
 const moveDown=editor.getByRole('button',{name:/Nach unten/}).first();
 await expect(moveDown).toHaveClass(/ghost/);
 await expect(moveDown).toHaveClass(/icon-button/);
});
