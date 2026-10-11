import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const DOCUMENT_ID='11111111-1111-1111-1111-111111111111';

async function setup(page,{language='de'}={}){
 await installApiMocks(page,{language});
 let row=null,documentsVisible=true;
 const document={id:DOCUMENT_ID,title:'Reisepass',mime_type:'application/pdf',file_url:`/api/documents/${DOCUMENT_ID}/file/`};

 await page.route('**/api/documents/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/documents/'&&route.request().method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(documentsVisible?[document]:[])});
  return route.continue();
 });
 await page.route('**/api/notes/**',route=>{
  const request=route.request(),method=request.method(),path=new URL(request.url()).pathname;
  const body=method==='GET'?{}:request.postDataJSON();
  const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  if(path==='/api/notes/'&&method==='GET')return json({results:row?[row]:[],next:null});
  if(path==='/api/notes/'&&method==='POST'){
   row={id:'note-doc-1',family:'family-1',author:1,title:'',body:'',drawing:[],shares:[],pinned:false,extended_mode:false,blocks:[],version:1,permission:'owner',...body};
   return json(row,201);
  }
  if(method==='PATCH'){
   row={...row,...body,version:row.version+1};
   return json(row);
  }
  if(method==='GET')return json(row);
  return json({},204);
 });
 await page.goto('/?page=notes');
 return {row:()=>row,revoke:()=>{documentsVisible=false}};
}

test('document references persist only the opaque id and re-resolve current document ACL',async({page})=>{
 const state=await setup(page);
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('button',{name:'Neue Notiz'}).click();
 await page.getByRole('button',{name:'Erweiterten Modus aktivieren'}).click();

 const picker=page.getByLabel('Dokument auswählen');
 await expect(picker).toContainText('Reisepass');
 await picker.selectOption(DOCUMENT_ID);
 await page.getByRole('button',{name:'Dokument verknüpfen'}).click();
 await expect(page.getByRole('status')).toContainText('Gespeichert');
 await expect(page.getByRole('link',{name:'Reisepass'})).toHaveAttribute('href',`/api/documents/${DOCUMENT_ID}/file/`);
 await expect.poll(()=>state.row().blocks).toEqual([{type:'document',document_id:DOCUMENT_ID}]);
 expect(JSON.stringify(state.row().blocks)).not.toContain('Reisepass');
 expect(JSON.stringify(state.row().blocks)).not.toContain('file_url');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);

 state.revoke();
 await page.reload();
 await page.getByRole('tab',{name:'Blöcke'}).click();
 await expect(page.getByText('Dokument nicht verfügbar')).toBeVisible();
 await expect(page.getByText('Reisepass')).toHaveCount(0);
});

test('document reference controls are translated in English',async({page})=>{
 await setup(page,{language:'en'});
 await page.getByRole('button',{name:'New note'}).click();
 await page.getByRole('button',{name:'Enable extended mode'}).click();
 await expect(page.getByLabel('Choose document')).toContainText('Reisepass');
 await expect(page.getByRole('button',{name:'Link document'})).toBeVisible();
});
