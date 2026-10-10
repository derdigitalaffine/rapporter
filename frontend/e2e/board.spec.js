import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,language='de'){
 await installApiMocks(page,{language});let rows=[];
 await page.route('**/api/board/**',async route=>{
  const request=route.request(),method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  if(method==='GET')return route.fulfill({json:{count:rows.length,next:null,results:rows}});
  if(method==='POST'){
   const raw=request.postData()||'';
   const text=raw.match(/name="text"\r\n\r\n([^]*?)\r\n--/)?.[1]||body.text||'';
   const row={id:'pin-1',family:'family-1',text,kind:body.kind||'note',target_id:null,target:null,position:0,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,can_reorder:true,images:[]};
   rows.unshift(row);return route.fulfill({status:201,json:row});
  }
  if(method==='PATCH'){rows[0]={...rows[0],...body};return route.fulfill({json:rows[0]})}
  if(method==='DELETE'){rows=[];return route.fulfill({status:204,body:''})}
 });
 await page.goto('/?page=board');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.app-shell')).toBeVisible();
}

test('pin note, edit, reload and remove it from the family pinboard',async({page})=>{
 await boot(page);
 await expect(page.getByRole('heading',{name:'Pinnwand',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Anpinnen',exact:true}).click();
 let form=page.locator('.pin-composer');await expect(form).toBeVisible();
 await form.getByLabel('Notizzettel',{exact:true}).fill('Wir treffen uns im Garten.');
 await form.getByRole('button',{name:'Anpinnen',exact:true}).click();
 const pin=page.locator('.pin-card').first();await expect(pin).toContainText('Wir treffen uns im Garten.');
 await pin.getByRole('button',{name:'Bearbeiten',exact:true}).click();
 form=page.locator('.pin-composer');await expect(form).toBeVisible();
 const editor=form.getByRole('textbox',{name:'Notizzettel',exact:true});await expect(editor).toBeFocused();
 await editor.fill('Wir treffen uns um 16 Uhr.');
 await form.getByRole('button',{name:'Speichern',exact:true}).click();
 await page.reload();await expect(page.locator('.pin-card')).toContainText('16 Uhr');
 await page.locator('.pin-card').getByRole('button',{name:'Entfernen',exact:true}).click();
 await page.getByRole('alertdialog').getByRole('button',{name:'Entfernen',exact:true}).click();
 await expect(page.locator('.pin-card')).toHaveCount(0);
});

test('English pinboard stays usable at 390px',async({page})=>{
 await page.setViewportSize({width:390,height:844});await boot(page,'en');
 await expect(page.getByRole('heading',{name:'Pinboard',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pin something',exact:true}).click();
 await expect(page.getByLabel('Note text',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
