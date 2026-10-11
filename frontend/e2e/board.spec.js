import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,language='de'){
 const state=await installApiMocks(page,{language});let rows=[];
 await page.route('**/api/board/**',async route=>{
  const request=route.request(),method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  if(method==='GET')return route.fulfill({json:{count:rows.length,next:null,results:rows}});
  if(method==='POST'){
   const raw=request.postData()||'';
   const text=raw.match(/name="text"\r\n\r\n([^]*?)\r\n--/)?.[1]||body.text||'';
   const row={id:`pin-${rows.length+1}`,family:'family-1',text,kind:body.kind||'note',target_id:body.target_id||null,target:null,position:0,author:1,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,can_reorder:true,images:[]};
   rows.unshift(row);return route.fulfill({status:201,json:row});
  }
  if(method==='PATCH'){rows[0]={...rows[0],...body};return route.fulfill({json:rows[0]})}
  if(method==='DELETE'){rows=[];return route.fulfill({status:204,body:''})}
 });
 await page.goto('/?page=board');
 return {rows,state};
}

test('pin note, edit, reload and remove it from the family pinboard',async({page})=>{
 await boot(page);
 await expect(page.getByRole('heading',{name:'Pinnwand',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Anpinnen',exact:true}).click();
 let form=page.locator('.pin-composer');await expect(form).toBeVisible();
 await form.getByLabel('Notizzettel',{exact:true}).fill('Wir treffen uns im Garten.');
 await form.getByRole('button',{name:'Anpinnen',exact:true}).click();
 const pin=page.locator('.pin-card').first();await expect(pin).toContainText('Wir treffen uns im Garten.');
 await expect(pin.locator('.pin-author')).toContainText('Angepinnt von Alex');
 await expect(pin.locator('.pin-author-avatar')).toHaveText('A');
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

test('composer pins a whole shopping list and provides searchable event choices',async({page})=>{
 await boot(page);
 await page.getByRole('button',{name:'Anpinnen',exact:true}).click();
 let form=page.locator('.pin-composer');
 await form.getByRole('button',{name:'Einkaufsliste',exact:true}).click();
 const listSelect=form.getByLabel('Vorhandenen Inhalt auswählen');
 await expect(listSelect).toContainText('Supermarkt');
 await listSelect.selectOption('shop-1');
 let requestPromise=page.waitForRequest(request=>request.url().endsWith('/api/board/')&&request.method()==='POST');
 await form.getByRole('button',{name:'Anpinnen',exact:true}).click();
 let request=await requestPromise;expect(request.postDataJSON()).toMatchObject({kind:'shopping_list',target_id:'shop-1'});

 await page.getByRole('button',{name:'Anpinnen',exact:true}).click();
 form=page.locator('.pin-composer');await form.getByRole('button',{name:'Termin',exact:true}).click();
 const search=form.getByRole('searchbox',{name:'Termine durchsuchen'});await expect(search).toBeVisible();await search.fill('Kinderarzt');
 const option=form.getByRole('option',{name:/Kinderarzt/});await expect(option).toBeVisible();await option.click();
 requestPromise=page.waitForRequest(value=>value.url().endsWith('/api/board/')&&value.method()==='POST');
 await form.getByRole('button',{name:'Anpinnen',exact:true}).click();
 request=await requestPromise;expect(request.postDataJSON()).toMatchObject({kind:'event',target_id:'event-1'});
});

test('school holiday pins show the full period and author identity',async({page})=>{
 const {rows,state}=await boot(page);
 const holiday={id:'holiday-1',family:'family-1',source:'school-source',type:'school.holiday',title:'Herbstferien',starts_at:'2026-10-12T00:00:00Z',ends_at:'2026-10-24T00:00:00Z',payload:{date_start:'2026-10-12',date_end_exclusive:'2026-10-24'}};
 state.events.push(holiday);rows.push({id:'pin-holiday',family:'family-1',text:'',kind:'event',target_id:'holiday-1',target:{id:'holiday-1',kind:'event',title:'Herbstferien',subtitle:holiday.starts_at,url:'/?page=calendar&event=holiday-1'},position:0,author:2,author_name:'Sam',created_at:new Date().toISOString(),can_edit:false,can_delete:true,can_reorder:true,images:[]});
 await page.reload();const pin=page.locator('#pin-pin-holiday');await expect(pin).toContainText('Ferien');await expect(pin).toContainText('Herbstferien');await expect(pin).toContainText(/12.*23/);await expect(pin.locator('.pin-author')).toContainText('Sam');
});

test('English pinboard stays usable at 390px',async({page})=>{
 await page.setViewportSize({width:390,height:844});await boot(page,'en');
 await expect(page.getByRole('heading',{name:'Pinboard',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pin something',exact:true}).click();
 await expect(page.getByLabel('Note text',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
