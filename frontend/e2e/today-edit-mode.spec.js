import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,{language='de'}={}){
 await installApiMocks(page,{language});
 let layout={
  version:2,
  revision:0,
  widgets:[
   {id:'week',visible:true,size:'wide',settings:{events:true,waste:true,holidays:true,special:true}},
   {id:'weather',visible:true,size:'medium'},
   {id:'priority',visible:true,size:'wide'},
   {id:'waste',visible:true,size:'medium'},
   {id:'next',visible:true,size:'medium'},
   {id:'shopping',visible:true,size:'compact'},
  ],
 };
 await page.route('**/api/today-layout/**',async route=>{
  if(route.request().method()==='PUT'){
   layout={...route.request().postDataJSON(),revision:layout.revision+1};
  }
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(layout)});
 });
 await page.goto('/');
 await expect(page.getByRole('button',{name:language==='de'?'Anpassen':'Customize'})).toBeEnabled();
 return {getLayout:()=>layout};
}

async function editorRows(editor){
 return editor.locator('[data-editor-widget-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.editorWidgetId));
}

async function visibleWidgets(page){
 return page.locator('[data-today-widget]').evaluateAll(nodes=>nodes.map(node=>node.dataset.todayWidget));
}

test('keyboard move mode reorders with live announcement and keeps focus',async({page})=>{
 await boot(page);
 await page.getByRole('button',{name:'Anpassen'}).click();
 const editor=page.getByRole('region',{name:'Anpassen'});
 const handle=editor.getByRole('button',{name:'Wetter · Verschieben'});
 const before=await editorRows(editor);
 const start=before.indexOf('weather');
 expect(start).toBeGreaterThanOrEqual(0);
 await handle.focus();
 await page.keyboard.press('Space');
 await expect(handle).toHaveAttribute('aria-pressed','true');
 await page.keyboard.press('ArrowDown');
 await expect(handle).toBeFocused();
 await expect(page.getByTestId('today-layout-live')).toContainText(`Position ${start+2}`);
 await page.keyboard.press('Space');
 await expect(handle).toHaveAttribute('aria-pressed','false');
 await expect(handle).toBeFocused();
 const after=await editorRows(editor);
 expect(after.indexOf('weather')).toBe(start+1);
});

test('Escape restores an active keyboard move, then cancels the editor',async({page})=>{
 await boot(page);
 await page.getByRole('button',{name:'Anpassen'}).click();
 const editor=page.getByRole('region',{name:'Anpassen'});
 const handle=editor.getByRole('button',{name:'Wetter · Verschieben'});
 const before=await editorRows(editor);
 await handle.focus();
 await page.keyboard.press('Enter');
 await page.keyboard.press('ArrowDown');
 expect(await editorRows(editor)).not.toEqual(before);
 await page.keyboard.press('Escape');
 expect(await editorRows(editor)).toEqual(before);
 await expect(editor).toBeVisible();
 await expect(handle).toBeFocused();
 await page.keyboard.press('Escape');
 await expect(editor).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Anpassen'})).toBeFocused();
});

test('pointer drag works only from the visible handle and persists on save',async({page})=>{
 const {getLayout}=await boot(page);
 await page.getByRole('button',{name:'Anpassen'}).click();
 const editor=page.getByRole('region',{name:'Anpassen'});
 const before=await editorRows(editor);
 const weatherIndex=before.indexOf('weather');
 const targetId=before[weatherIndex+1];
 expect(targetId).toBeTruthy();
 const handle=editor.getByTestId('today-drag-weather');
 const target=editor.locator(`[data-editor-widget-id="${targetId}"]`);
 const handleBox=await handle.boundingBox();
 const targetBox=await target.boundingBox();
 expect(handleBox).not.toBeNull();
 expect(targetBox).not.toBeNull();
 await page.mouse.move(handleBox.x+handleBox.width/2,handleBox.y+handleBox.height/2);
 await page.mouse.down();
 await page.mouse.move(targetBox.x+targetBox.width/2,targetBox.y+targetBox.height/2,{steps:5});
 await page.mouse.up();
 const after=await editorRows(editor);
 expect(after.indexOf('weather')).toBe(weatherIndex+1);
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(editor).toHaveCount(0);
 expect(getLayout().widgets.map(row=>row.id).indexOf('weather')).toBe(weatherIndex+1);
});

test('touch drag uses the same visible handle and reorders without a drag-only contract',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await boot(page);
 await page.getByRole('button',{name:'Anpassen'}).click();
 const editor=page.getByRole('region',{name:'Anpassen'});
 const before=await editorRows(editor);
 const weatherIndex=before.indexOf('weather');
 const targetId=before[weatherIndex+1];
 expect(targetId).toBeTruthy();
 const handle=editor.getByTestId('today-drag-weather');
 const target=editor.locator(`[data-editor-widget-id="${targetId}"]`);
 const handleBox=await handle.boundingBox();
 const targetBox=await target.boundingBox();
 expect(handleBox).not.toBeNull();
 expect(targetBox).not.toBeNull();
 const startX=handleBox.x+handleBox.width/2;
 const startY=handleBox.y+handleBox.height/2;
 const targetX=targetBox.x+targetBox.width/2;
 const targetY=targetBox.y+targetBox.height/2;
 await handle.dispatchEvent('pointerdown',{pointerId:61,pointerType:'touch',isPrimary:true,button:0,clientX:startX,clientY:startY});
 await handle.dispatchEvent('pointermove',{pointerId:61,pointerType:'touch',isPrimary:true,buttons:1,clientX:targetX,clientY:targetY});
 await handle.dispatchEvent('pointerup',{pointerId:61,pointerType:'touch',isPrimary:true,button:0,clientX:targetX,clientY:targetY});
 expect((await editorRows(editor)).indexOf('weather')).toBe(weatherIndex+1);
 await expect(editor.getByRole('button',{name:'Wetter · Nach oben'})).toBeEnabled();
});

test('touch long press enters edit mode focused without moving the widget',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await boot(page);
 const before=await visibleWidgets(page);
 const widget=page.locator('[data-today-widget="week"]');
 await expect(widget).toBeVisible();
 const box=await widget.boundingBox();
 expect(box).not.toBeNull();
 const x=box.x+Math.min(24,box.width/2);
 const y=box.y+Math.min(24,box.height/2);
 await widget.dispatchEvent('pointerdown',{pointerId:41,pointerType:'touch',isPrimary:true,button:0,clientX:x,clientY:y});
 await page.waitForTimeout(600);
 const editor=page.getByRole('region',{name:'Anpassen'});
 await expect(editor).toBeVisible();
 const handle=editor.getByRole('button',{name:'Wochenkompass · Verschieben'});
 await expect(handle).toBeFocused();
 const handleBox=await handle.boundingBox();
 expect(handleBox.width).toBeGreaterThanOrEqual(44);
 expect(handleBox.height).toBeGreaterThanOrEqual(44);
 await editor.getByRole('button',{name:'Abbrechen',exact:true}).click();
 expect(await visibleWidgets(page)).toEqual(before);
});

test('touch movement cancels long press so normal scrolling is not captured',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await boot(page);
 const widget=page.locator('[data-today-widget="week"]');
 await expect(widget).toBeVisible();
 const box=await widget.boundingBox();
 expect(box).not.toBeNull();
 const x=box.x+20;
 const y=box.y+20;
 await widget.dispatchEvent('pointerdown',{pointerId:51,pointerType:'touch',isPrimary:true,button:0,clientX:x,clientY:y});
 await widget.dispatchEvent('pointermove',{pointerId:51,pointerType:'touch',isPrimary:true,buttons:1,clientX:x,clientY:y+30});
 await page.waitForTimeout(600);
 await expect(page.getByRole('region',{name:'Anpassen'})).toHaveCount(0);
});
