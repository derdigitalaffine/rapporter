import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function setup(page,{language='de',conflict=false,permission='owner'}={}){
 await installApiMocks(page,{language});let row=null;let taskCounter=0;
 await page.route('**/api/notes/**',async route=>{
  const request=route.request(),method=request.method(),path=new URL(request.url()).pathname;
  const body=method==='GET'?{}:request.postDataJSON();
  const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  if(path==='/api/notes/'&&method==='GET')return json({results:row?[row]:[],next:null});
  if(path==='/api/notes/'&&method==='POST'){
   row={id:'note-1',family:'family-1',author:1,title:'',body:'',drawing:[],shares:[],pinned:false,extended_mode:false,blocks:[],version:1,permission,...body};
   return json(row,201);
  }
  if(path.endsWith('/checklist-task/')&&method==='POST'){
   taskCounter+=1;
   const taskId=`00000000-0000-0000-0000-${String(taskCounter).padStart(12,'0')}`;
   row={...row,blocks:(row.blocks||[]).map(block=>block.type==='checklist'?{...block,items:block.items.map(item=>item.id===body.item_id?{...item,task_id:taskId}:item)}:block),version:row.version+1};
   return json({created:true,task:{id:taskId,title:'Pack passport'},note:row},201);
  }
  if(path.endsWith('/sharing/')){row={...row,shares:body.shares,version:row.version+1};return json(row)}
  if(method==='PATCH'){if(conflict)return json({detail:'note_conflict'},409);row={...row,...body,version:row.version+1};return json(row)}
  if(method==='GET')return json(row);
  return json({},204);
 });
 await page.goto('/?page=notes');return()=>row;
}

test('private note uses touch Markdown editor and direct member sharing survives reload',async({page})=>{
 const row=await setup(page);await page.getByRole('button',{name:'Neue Notiz'}).click();
 await expect(page.getByRole('tab',{name:'Blöcke'})).toHaveCount(0);
 await expect(page.locator('.note-md-editor .w-md-editor-toolbar').first()).toBeVisible();
 await page.getByRole('textbox',{name:'Titel',exact:true}).fill('Packliste');
 await page.getByRole('textbox',{name:'Text',exact:true}).fill('**Wichtig**\n- [ ] Reisepass');
 await expect(page.getByRole('status')).toContainText('Gespeichert');
 await page.getByRole('tab',{name:'Vorschau',exact:true}).click();await expect(page.locator('.note-preview strong')).toHaveText('Wichtig');
 await page.getByRole('button',{name:'Freigaben',exact:true}).click();const sam=page.locator('.note-share-row').filter({hasText:'Sam'});
 await sam.getByRole('button',{name:'Lesen',exact:true}).click();await expect.poll(()=>row().shares).toEqual([{user:2,permission:'read'}]);
 await sam.getByRole('button',{name:'Bearbeiten',exact:true}).click();await expect.poll(()=>row().shares).toEqual([{user:2,permission:'edit'}]);
 await page.reload();await expect(page.getByRole('textbox',{name:'Titel',exact:true})).toHaveValue('Packliste');
});

test('extended checklist stays in the note until explicit task conversion and is mobile safe',async({page})=>{
 const row=await setup(page);await page.setViewportSize({width:390,height:844});
 await page.getByRole('button',{name:'Neue Notiz'}).click();
 await page.getByRole('button',{name:'Erweiterten Modus aktivieren'}).click();
 await expect(page.getByRole('tab',{name:'Blöcke'})).toBeVisible();
 await page.getByRole('button',{name:'Checkliste',exact:true}).click();
 await page.getByRole('button',{name:'Punkt hinzufügen'}).click();
 const item=page.locator('.note-checklist-item').first();
 await item.getByRole('textbox',{name:'Eintrag'}).fill('Pass einpacken');
 await item.getByLabel('Zuweisung').selectOption('2');
 await item.getByLabel('Fällig').fill('2030-01-02T12:00');
 await expect(page.getByRole('status')).toContainText('Gespeichert');
 expect(row().blocks[0].items[0].task_id).toBeUndefined();
 await item.getByRole('button',{name:'In Aufgabe umwandeln'}).focus();
 await page.keyboard.press('Enter');
 await expect(item.getByText('Aufgabe erstellt')).toBeVisible();
 await expect.poll(()=>row().blocks[0].items[0].task_id).toBeTruthy();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('extended controls are translated in English',async({page})=>{
 await setup(page,{language:'en'});await page.getByRole('button',{name:'New note'}).click();
 await page.getByRole('button',{name:'Enable extended mode'}).click();
 await expect(page.getByRole('tab',{name:'Blocks'})).toBeVisible();
 await page.getByRole('button',{name:'Checklist',exact:true}).click();
 await expect(page.getByRole('button',{name:'Add item'})).toBeVisible();
});

test('drawing pointer strokes autosave and undo safely',async({page})=>{
 const row=await setup(page);await page.getByRole('button',{name:'Neue Notiz'}).click();await page.getByRole('tab',{name:'Zeichnen',exact:true}).click();const rect=await page.locator('.note-drawing svg').boundingBox();await page.mouse.move(rect.x+30,rect.y+30);await page.mouse.down();await page.mouse.move(rect.x+80,rect.y+80,{steps:5});await page.mouse.up();await expect.poll(()=>row().drawing.length).toBe(1);await page.getByRole('button',{name:'Rückgängig',exact:true}).click();await expect.poll(()=>row().drawing.length).toBe(0);
});

test('conflict keeps local content and English editor is usable',async({page})=>{
 await setup(page,{language:'en',conflict:true});await page.getByRole('button',{name:'New note'}).click();await page.getByRole('textbox',{name:'Text',exact:true}).fill('Never lose this');await expect(page.getByRole('alert')).toContainText('changed elsewhere');await expect(page.getByRole('textbox',{name:'Text',exact:true})).toHaveValue('Never lose this');await expect(page.getByRole('button',{name:'Save my changes as a private copy'})).toBeVisible();
});

test('unsaved conflict blocks shell navigation without losing the local note',async({page})=>{
 await setup(page,{language:'en',conflict:true});await page.getByRole('button',{name:'New note'}).click();await page.getByRole('textbox',{name:'Text',exact:true}).fill('Keep my draft');await expect(page.getByRole('alert')).toContainText('changed elsewhere');await page.locator('.bottom-nav').getByRole('button',{name:'Today',exact:true}).click();await expect(page.getByRole('textbox',{name:'Text',exact:true})).toHaveValue('Keep my draft');await expect(page).toHaveURL(/page=notes/);
});
