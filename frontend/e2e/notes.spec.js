import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
async function setup(page,{language='de',conflict=false,permission='owner'}={}){
 await installApiMocks(page,{language});let row=null;
 await page.route('**/api/notes/**',async route=>{const request=route.request(),method=request.method(),path=new URL(request.url()).pathname;const body=method==='GET'?{}:request.postDataJSON();const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 if(path==='/api/notes/'&&method==='GET')return json({results:row?[row]:[],next:null});
 if(path==='/api/notes/'&&method==='POST'){row={id:'note-1',family:'family-1',author:1,title:'',body:'',drawing:[],shares:[],pinned:false,version:1,permission,...body};return json(row,201)}
 if(path.endsWith('/sharing/')){row={...row,shares:body.shares,version:row.version+1};return json(row)}
 if(method==='PATCH'){if(conflict)return json({detail:'note_conflict'},409);row={...row,...body,version:row.version+1};return json(row)}
 if(method==='GET')return json(row);return json({},204)});
 await page.goto('/?page=notes');return()=>row;
}
test('private note autosaves Markdown and selected member sharing survives reload',async({page})=>{
 const row=await setup(page);await page.getByRole('button',{name:'Neue Notiz'}).click();await page.getByRole('textbox',{name:'Titel',exact:true}).fill('Packliste');await page.getByRole('textbox',{name:'Text',exact:true}).fill('**Wichtig**\n- [ ] Reisepass');await expect(page.getByRole('status')).toContainText('Gespeichert');await page.getByRole('button',{name:'Vorschau',exact:true}).click();await expect(page.locator('.note-preview strong')).toHaveText('Wichtig');await page.getByRole('button',{name:'Freigaben',exact:true}).click();await page.getByRole('combobox',{name:'Freigaben Sam'}).selectOption('read');await expect.poll(()=>row().shares).toEqual([{user:2,permission:'read'}]);await page.reload();await expect(page.getByRole('textbox',{name:'Titel',exact:true})).toHaveValue('Packliste');
});
test('drawing pointer strokes autosave and undo safely',async({page})=>{
 const row=await setup(page);await page.getByRole('button',{name:'Neue Notiz'}).click();await page.getByRole('button',{name:'Zeichnen',exact:true}).click();const rect=await page.locator('.note-drawing svg').boundingBox();await page.mouse.move(rect.x+30,rect.y+30);await page.mouse.down();await page.mouse.move(rect.x+80,rect.y+80,{steps:5});await page.mouse.up();await expect.poll(()=>row().drawing.length).toBe(1);await page.getByRole('button',{name:'Rückgängig',exact:true}).click();await expect.poll(()=>row().drawing.length).toBe(0);
});
test('conflict keeps local content and English editor is usable',async({page})=>{
 await setup(page,{language:'en',conflict:true});await page.getByRole('button',{name:'New note'}).click();await page.getByRole('textbox',{name:'Text',exact:true}).fill('Never lose this');await expect(page.getByRole('alert')).toContainText('changed elsewhere');await expect(page.getByRole('textbox',{name:'Text',exact:true})).toHaveValue('Never lose this');await expect(page.getByRole('button',{name:'Save my changes as a private copy'})).toBeVisible();
});
