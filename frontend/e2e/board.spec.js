import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const PICKER_KINDS={calendar_event:'event',task:'task',routine:'routine',note:'note_ref',shopping_item:'shopping',shopping_list:'shopping_list',trip:'trip',document:'document'};

function pickerRows(state,key){
 if(key==='calendar_event')return state.events.map(row=>({id:row.id,kind:'event',title:row.title,subtitle:row.starts_at,event_type:row.type,ends_at:row.ends_at,date_start:row.payload?.date_start,date_end_exclusive:row.payload?.date_end_exclusive,url:`/?page=calendar&event=${row.id}`}));
 if(key==='task')return state.tasks.filter(row=>!row.completed_at).map(row=>({id:row.id,kind:'task',title:row.title,subtitle:row.due_at,url:`/?page=tasks&task=${row.id}`}));
 if(key==='routine')return [{id:'routine-1',kind:'routine',title:'Müll rausstellen',subtitle:null,url:'/?page=tasks&routine=routine-1'}];
 if(key==='note')return [{id:'note-1',kind:'note_ref',title:'Familiennotiz',subtitle:'Kurzer Hinweis',url:'/?page=notes&note=note-1'}];
 if(key==='shopping_item')return state.shoppingLists.flatMap(list=>list.items.map(item=>({id:item.id,kind:'shopping',title:item.name,subtitle:list.name,url:'/?page=shopping'})));
 if(key==='shopping_list')return state.shoppingLists.map(list=>({id:list.id,kind:'shopping_list',title:list.name,subtitle:list.store,url:`/?page=shopping&list=${list.id}`}));
 if(key==='trip')return [{id:'trip-1',kind:'trip',title:'Herbstreise',subtitle:'Hamburg',url:'/?page=travel&trip=trip-1'}];
 if(key==='document')return [{id:'document-1',kind:'document',title:'Versicherung',subtitle:'Muster AG',url:'/api/documents/document-1/file/'}];
 return [];
}

async function boot(page,language='de'){
 const state=await installApiMocks(page,{language});let rows=[];
 await page.route('**/api/board/**',async route=>{
  const request=route.request(),method=request.method(),url=new URL(request.url()),path=url.pathname;let body={};try{body=request.postDataJSON()||{}}catch{}
  if(path==='/api/board/picker/'&&method==='GET'){
   const key=url.searchParams.get('adapter_key');const q=(url.searchParams.get('q')||'').toLocaleLowerCase();
   const results=pickerRows(state,key).filter(row=>!q||`${row.title||''} ${row.subtitle||''}`.toLocaleLowerCase().includes(q));
   return route.fulfill({json:{kind:PICKER_KINDS[key],adapter_key:key,page:Number(url.searchParams.get('page')||1),page_size:20,has_next:false,results}});
  }
  if(path==='/api/board/'&&method==='GET')return route.fulfill({json:{count:rows.length,next:null,results:rows}});
  if(path==='/api/board/'&&method==='POST'){
   const raw=request.postData()||'';
   const text=raw.match(/name="text"\r\n\r\n([^]*?)\r\n--/)?.[1]||body.text||'';
   const row={id:`pin-${rows.length+1}`,family:'family-1',text,kind:body.kind||'note',adapter_key:body.adapter_key||'',target_id:body.target_id||null,target:null,visibility:'family',selected_membership_ids:[],effective_scope:'family',position:0,author:1,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,can_reorder:true,can_change_pin_visibility:true,can_share_source:false,can_interact:true,images:[]};
   rows.unshift(row);return route.fulfill({status:201,json:row});
  }
  if(/^\/api\/board\/[^/]+\/$/.test(path)&&method==='PATCH'){rows[0]={...rows[0],...body};return route.fulfill({json:rows[0]})}
  if(/^\/api\/board\/[^/]+\/$/.test(path)&&method==='DELETE'){rows=[];return route.fulfill({status:204,body:''})}
  return route.fulfill({status:404,json:{detail:'not found'}});
 });
 await page.goto('/?page=board');
 return {rows,state};
}

function photoPin(id='pin-photo'){
 return {id,family:'family-1',text:'Ausflug',kind:'photo',adapter_key:'',target_id:null,target:null,visibility:'family',selected_membership_ids:[],effective_scope:'family',position:0,author:1,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,can_reorder:true,can_change_pin_visibility:true,can_share_source:false,can_interact:true,images:[{id:'image-1',url:'/api/board-images/image-1/',width:1200,height:900},{id:'image-2',url:'/api/board-images/image-2/',width:900,height:1200}]};
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

test('composer pins shopping lists and events only through the canonical picker',async({page})=>{
 await boot(page);
 await page.getByRole('button',{name:'Anpinnen',exact:true}).click();
 let form=page.locator('.pin-composer');
 await expect(form.getByRole('button',{name:'Notizzettel',exact:true})).toBeVisible();
 await expect(form.getByRole('button',{name:'Foto',exact:true})).toBeVisible();
 await form.getByRole('button',{name:'Vorhandenes Objekt',exact:true}).click();
 await form.getByRole('button',{name:'Einkauf',exact:true}).click();
 await form.getByRole('button',{name:'Einkaufslisten',exact:true}).click();
 await form.getByRole('button',{name:/Supermarkt · Markt/}).click();
 let requestPromise=page.waitForRequest(request=>request.url().endsWith('/api/board/')&&request.method()==='POST');
 await form.getByRole('button',{name:'Anpinnen',exact:true}).click();
 let request=await requestPromise;expect(request.postDataJSON()).toMatchObject({kind:'shopping_list',adapter_key:'shopping_list',target_id:'shop-1'});expect(request.postDataJSON()).not.toHaveProperty('visibility');

 await page.getByRole('button',{name:'Anpinnen',exact:true}).click();
 form=page.locator('.pin-composer');await form.getByRole('button',{name:'Vorhandenes Objekt',exact:true}).click();await form.getByRole('button',{name:'Kalender',exact:true}).click();
 const search=form.getByRole('searchbox',{name:'Vorhandenen Inhalt auswählen'});await expect(search).toBeVisible();await search.fill('Kinderarzt');
 const option=form.getByRole('button',{name:/Kinderarzt/});await expect(option).toBeVisible();await option.click();
 requestPromise=page.waitForRequest(value=>value.url().endsWith('/api/board/')&&value.method()==='POST');
 await form.getByRole('button',{name:'Anpinnen',exact:true}).click();
 request=await requestPromise;expect(request.postDataJSON()).toMatchObject({kind:'event',adapter_key:'calendar_event',target_id:'event-1'});expect(request.postDataJSON()).not.toHaveProperty('visibility');
});

test('school holiday pins show the full period and author identity from canonical target preview',async({page})=>{
 const {rows,state}=await boot(page);
 const holiday={id:'holiday-1',family:'family-1',source:'school-source',type:'school.holiday',title:'Herbstferien',starts_at:'2026-10-12T00:00:00Z',ends_at:'2026-10-24T00:00:00Z',payload:{date_start:'2026-10-12',date_end_exclusive:'2026-10-24'}};
 state.events.push(holiday);rows.push({id:'pin-holiday',family:'family-1',text:'',kind:'event',adapter_key:'calendar_event',target_id:'holiday-1',target:{id:'holiday-1',kind:'event',title:'Herbstferien',subtitle:holiday.starts_at,event_type:'school.holiday',ends_at:holiday.ends_at,date_start:'2026-10-12',date_end_exclusive:'2026-10-24',url:'/?page=calendar&event=holiday-1'},visibility:'family',selected_membership_ids:[],effective_scope:'family',position:0,author:2,author_name:'Sam',created_at:new Date().toISOString(),can_edit:false,can_delete:true,can_reorder:true,can_change_pin_visibility:false,can_share_source:false,can_interact:true,images:[]});
 await page.reload();const pin=page.locator('#pin-pin-holiday');await expect(pin).toContainText('Ferien');await expect(pin).toContainText('Herbstferien');await expect(pin).toContainText(/12.*23/);await expect(pin.locator('.pin-author')).toContainText('Sam');
});

test('pinboard photos stay inside the PWA and support keyboard gallery navigation',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const {rows}=await boot(page);rows.push(photoPin());await page.reload();
 const first=page.locator('#pin-pin-photo .pin-photos a').first();const popups=[];page.on('popup',popup=>popups.push(popup));
 await first.click();expect(popups).toHaveLength(0);
 const dialog=page.getByRole('dialog',{name:'Fotoansicht'});await expect(dialog).toBeVisible();await expect(dialog.getByText('Foto 1 von 2',{exact:true})).toBeVisible();
 await expect(dialog.getByRole('button',{name:'Fotoansicht schließen'})).toBeFocused();await expect(dialog.getByRole('button',{name:'Vorheriges Foto'})).toBeDisabled();
 await page.keyboard.press('ArrowRight');await expect(dialog.getByText('Foto 2 von 2',{exact:true})).toBeVisible();await expect(dialog.getByRole('button',{name:'Nächstes Foto'})).toBeDisabled();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(first).toBeFocused();
});

test('English photo viewer exposes localized accessible controls',async({page})=>{
 const {rows}=await boot(page,'en');rows.push(photoPin('pin-photo-en'));await page.reload();
 await page.locator('#pin-pin-photo-en .pin-photos a').first().click();
 const dialog=page.getByRole('dialog',{name:'Photo viewer'});await expect(dialog).toBeVisible();await expect(dialog.getByRole('button',{name:'Close photo viewer'})).toBeVisible();await expect(dialog.getByRole('button',{name:'Next photo'})).toBeVisible();
});

test('English pinboard stays usable at 390px',async({page})=>{
 await page.setViewportSize({width:390,height:844});await boot(page,'en');
 await expect(page.getByRole('heading',{name:'Pinboard',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pin something',exact:true}).click();
 await expect(page.getByLabel('Note text',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
