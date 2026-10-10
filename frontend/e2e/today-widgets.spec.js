import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
const ids=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes'];
async function boot(page,{language='de',failSave=false,conflict=false,routines=[]}={}){
 const state=await installApiMocks(page,{language});state.routines=routines;
 let layout={version:1,revision:0,widgets:ids.map(id=>({id,visible:true,size:'full'}))};
 await page.route('**/api/today-layout/**',async route=>{
  const method=route.request().method();
  if(method==='PUT'){
   if(failSave)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Unavailable'})});
   if(conflict)return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Layout changed on another device.'})});
   layout={...route.request().postDataJSON(),revision:layout.revision+1};
  }
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(layout)});
 });
 await page.goto('/');await expect(page.getByRole('button',{name:language==='de'?'Raster bearbeiten':'Edit grid'})).toBeEnabled();
}
test('personal Today preview cancels and saves hidden widgets across reload',async({page})=>{
 await boot(page);await page.getByRole('button',{name:'Raster bearbeiten'}).click();
 const editor=page.getByRole('region',{name:'Raster bearbeiten'});
 await editor.getByLabel('Aufgaben',{exact:true}).uncheck();
 await expect(page.locator('[data-today-widget="tasks"]')).toHaveCount(0);
 await editor.getByRole('button',{name:'Abbrechen',exact:true}).click();
 await expect(page.locator('[data-today-widget="tasks"]')).toBeVisible();
 await page.getByRole('button',{name:'Raster bearbeiten'}).click();
 await editor.getByLabel('Aufgaben',{exact:true}).uncheck();
 await editor.getByRole('button',{name:'Einkauf · Nach oben',exact:true}).click();
 await editor.getByRole('combobox',{name:'Einkauf · Größe'}).selectOption('compact');
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();await expect(editor).toHaveCount(0);
 await page.reload();await expect(page.getByRole('button',{name:'Raster bearbeiten'}).toBeEnabled();
 await expect(page.locator('[data-today-widget="tasks"]')).toHaveCount(0);
 await expect(page.locator('[data-today-widget="shopping"]')).toHaveClass(/today-widget-compact/);
 await page.getByRole('button',{name:'Raster bearbeiten'}).click();
 await editor.getByRole('button',{name:'Standard wiederherstellen'}).click();
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(page.locator('[data-today-widget="tasks"]')).toBeVisible();
});
test('square size is offered for suitable widgets but not dense task lists',async({page})=>{
 await boot(page);await page.getByRole('button',{name:'Raster bearbeiten'}).click();
 const editor=page.getByRole('region',{name:'Raster bearbeiten'});
 const weatherSize=editor.getByRole('combobox',{name:'Wetter · Größe'});
 await expect(weatherSize.locator('option[value="square"]')).toHaveCount(1);
 await weatherSize.selectOption('square');
 await expect(page.locator('[data-today-widget="weather"]')).toHaveAttribute('data-widget-size','square');
 const taskSize=editor.getByRole('combobox',{name:'Aufgaben · Größe'});
 await expect(taskSize.locator('option[value="square"]')).toHaveCount(0);
});
test('routines stay visible on Today even while prediction is still learning',async({page})=>{
 await boot(page,{routines:[{id:'routine-1',family:'family-1',name:'Spülmaschine',active:true,last_done_at:new Date().toISOString(),prediction:{status:'learning'}}]});
 const widget=page.locator('[data-today-widget="routines"]');await expect(widget).toBeVisible();await expect(widget.getByText('Spülmaschine',{exact:true})).toBeVisible();
});
test('routines widget remains available as an empty entry point',async({page})=>{
 await boot(page);const widget=page.locator('[data-today-widget="routines"]');await expect(widget).toBeVisible();await expect(widget.getByTestId('today-routines')).toBeVisible();
});
test('failed save preserves draft and concurrent edits require reload',async({page})=>{
 await boot(page,{conflict:true});await page.getByRole('button',{name:'Raster bearbeiten'}).click();
 const editor=page.getByRole('region',{name:'Raster bearbeiten'});await editor.getByLabel('Einkauf',{exact:true}).uncheck();
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('anderen Gerät');
 await expect(editor).toBeVisible();await expect(editor.getByRole('button',{name:'Speichern',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Erneut laden'}).click();await expect(editor).toHaveCount(0);
});
test('English grid editor fits narrow view and is keyboard operable',async({page})=>{
 await page.setViewportSize({width:360,height:800});await boot(page,{language:'en'});
 await page.getByRole('button',{name:'Edit grid'}).click();
 const editor=page.getByRole('region',{name:'Edit grid'});
 const checkbox=editor.getByLabel('Tasks',{exact:true});await checkbox.focus();await page.keyboard.press('Space');await expect(checkbox).not.toBeChecked();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await editor.getByRole('button',{name:'Cancel',exact:true}).click();await expect(page.locator('[data-today-widget="tasks"]')).toBeVisible();
});
test('temporary save error keeps edited visibility for retry',async({page})=>{
 await boot(page,{failSave:true});await page.getByRole('button',{name:'Raster bearbeiten'}).click();
 const editor=page.getByRole('region',{name:'Raster bearbeiten'});await editor.getByLabel('Einkauf',{exact:true}).uncheck();
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Entwurf bleibt erhalten');
 await expect(editor.getByLabel('Einkauf',{exact:true})).not.toBeChecked();
 await expect(editor.getByRole('button',{name:'Speichern',exact:true})).toBeEnabled();
});