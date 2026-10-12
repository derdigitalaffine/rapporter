import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const LEGACY={calendar_event:'event',task:'task',routine:'routine',note:'note_ref',shopping_item:'shopping',shopping_list:'shopping_list',trip:'trip',document:'document'};
const TITLES={calendar_event:'Elternabend',task:'Wäsche',routine:'Müll rausstellen',note:'Packliste',shopping_item:'Milch',shopping_list:'Supermarkt',trip:'Hamburg',document:'Versicherung'};

async function boot(page,{language='de',picker}={}){
 await installApiMocks(page,{language});
 const state={pickerRequests:[],posts:[]};
 await page.route('**/api/board/**',async route=>{
  const request=route.request(),method=request.method(),url=new URL(request.url()),path=url.pathname;
  if(path==='/api/board/picker/'&&method==='GET'){
   const key=url.searchParams.get('adapter_key'),pageNumber=Number(url.searchParams.get('page')||1),query=url.searchParams.get('q')||'';
   state.pickerRequests.push({key,page:pageNumber,query});
   if(picker)return picker({route,key,page:pageNumber,query,state});
   const row={id:`${key}-1`,kind:LEGACY[key],title:TITLES[key],subtitle:key==='document'?'Muster AG':null,url:'/?page=example'};
   return route.fulfill({json:{kind:LEGACY[key],adapter_key:key,page:pageNumber,page_size:20,has_next:false,results:[row]}});
  }
  if(path==='/api/board/'&&method==='GET')return route.fulfill({json:{count:0,next:null,results:[]}});
  if(path==='/api/board/'&&method==='POST'){
   let body=null;try{body=request.postDataJSON()}catch{body=request.postData()||''}state.posts.push(body);
   return route.fulfill({status:201,json:{id:'pin-new',family:'family-1',kind:body?.kind||'photo',adapter_key:body?.adapter_key||'',target_id:body?.target_id||null,text:body?.text||'',target:null,visibility:'family',selected_membership_ids:[],effective_scope:'family',position:0,author:1,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,can_reorder:true,can_change_pin_visibility:true,can_interact:true,images:[]}});
  }
  return route.fulfill({status:404,json:{detail:'not found'}});
 });
 await page.goto('/?page=board');
 await page.getByRole('button',{name:language==='en'?'Pin something':'Anpinnen',exact:true}).click();
 return state;
}

async function chooseExisting(form){await form.getByRole('button',{name:'Vorhandenes Objekt',exact:true}).click()}

test('composer exposes exactly three roots and reaches all eight canonical adapters',async({page})=>{
 const state=await boot(page);const form=page.locator('.pin-composer');
 const roots=form.locator('.pin-composer-root-grid > button');await expect(roots).toHaveCount(3);
 await expect(roots.nth(0)).toContainText('Notizzettel');await expect(roots.nth(1)).toContainText('Foto');await expect(roots.nth(2)).toContainText('Vorhandenes Objekt');
 await chooseExisting(form);await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('task');
 await form.getByRole('button',{name:'Routinen',exact:true}).click();await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('routine');
 await form.getByRole('button',{name:'Kalender',exact:true}).click();await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('calendar_event');
 await form.getByRole('button',{name:'Einkauf',exact:true}).click();await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('shopping_item');
 await form.getByRole('button',{name:'Einkaufslisten',exact:true}).click();await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('shopping_list');
 await form.getByRole('button',{name:'Dokumente',exact:true}).click();await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('document');
 await form.getByRole('button',{name:'Weitere',exact:true}).click();await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('note');
 await form.getByRole('button',{name:'Reisen',exact:true}).click();await expect.poll(()=>state.pickerRequests.map(row=>row.key)).toContain('trip');
 expect(new Set(state.pickerRequests.map(row=>row.key))).toEqual(new Set(Object.keys(LEGACY)));
});

test('server search, pagination and submission keep canonical adapter identity',async({page})=>{
 const state=await boot(page,{picker:async({route,key,page,query})=>{
  if(key!=='task')return route.fulfill({json:{kind:LEGACY[key],adapter_key:key,page,page_size:20,has_next:false,results:[]}});
  const all=query?[{id:'task-search',kind:'task',title:`Treffer ${query}`,subtitle:null,url:'/?page=tasks'}]:page===1?[{id:'task-1',kind:'task',title:'Erste Aufgabe',subtitle:null,url:'/?page=tasks'}]:[{id:'task-2',kind:'task',title:'Zweite Aufgabe',subtitle:null,url:'/?page=tasks'}];
  return route.fulfill({json:{kind:'task',adapter_key:'task',page,page_size:20,has_next:!query&&page===1,results:all}});
 }});
 const form=page.locator('.pin-composer');await chooseExisting(form);
 await expect(form.getByRole('button',{name:'Erste Aufgabe',exact:true})).toBeVisible();await form.getByRole('button',{name:'Weitere laden',exact:true}).click();await expect(form.getByRole('button',{name:'Zweite Aufgabe',exact:true})).toBeVisible();
 const search=form.getByRole('searchbox',{name:'Vorhandenen Inhalt auswählen'});await search.fill('arzt');await expect(form.getByRole('button',{name:'Treffer arzt',exact:true})).toBeVisible();
 await form.getByRole('button',{name:'Treffer arzt',exact:true}).click();await form.getByRole('button',{name:'Anpinnen',exact:true}).click();
 expect(state.posts.at(-1)).toMatchObject({kind:'task',adapter_key:'task',target_id:'task-search'});
 expect(state.pickerRequests.some(row=>row.key==='task'&&row.page===2)).toBeTruthy();expect(state.pickerRequests.some(row=>row.key==='task'&&row.query==='arzt')).toBeTruthy();
});

test('late search responses and auth loss cannot restore stale private selection',async({page})=>{
 let releaseOld;const oldGate=new Promise(resolve=>{releaseOld=resolve});
 await boot(page,{picker:async({route,key,page,query})=>{
  if(query==='alt'){await oldGate;return route.fulfill({json:{kind:LEGACY[key],adapter_key:key,page,page_size:20,has_next:false,results:[{id:'old',kind:LEGACY[key],title:'Alter privater Treffer'}]}})}
  if(query==='neu')return route.fulfill({json:{kind:LEGACY[key],adapter_key:key,page,page_size:20,has_next:false,results:[{id:'new',kind:LEGACY[key],title:'Neuer Treffer'}]}});
  return route.fulfill({json:{kind:LEGACY[key],adapter_key:key,page,page_size:20,has_next:false,results:[]}});
 }});
 const form=page.locator('.pin-composer');await chooseExisting(form);const search=form.getByRole('searchbox',{name:'Vorhandenen Inhalt auswählen'});
 await search.fill('alt');await page.waitForTimeout(220);await search.fill('neu');await expect(form.getByRole('button',{name:'Neuer Treffer',exact:true})).toBeVisible();releaseOld();await page.waitForTimeout(250);await expect(form.getByText('Alter privater Treffer',{exact:true})).toHaveCount(0);
 await form.getByRole('button',{name:'Neuer Treffer',exact:true}).click();await expect(form.getByRole('button',{name:'Anpinnen',exact:true})).toBeEnabled();
 await page.evaluate(()=>window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:false}})));await expect(form.getByRole('button',{name:'Anpinnen',exact:true})).toBeDisabled();await expect(form.getByText('Neuer Treffer',{exact:true})).toHaveCount(0);
});

test('photo root keeps the existing secure upload flow at 390px',async({page})=>{
 await page.setViewportSize({width:390,height:844});const state=await boot(page);const form=page.locator('.pin-composer');await form.getByRole('button',{name:'Foto',exact:true}).click();
 await form.getByLabel('Fotos hinzufügen').setInputFiles({name:'familie.jpg',mimeType:'image/jpeg',buffer:Buffer.from('fake-jpeg')});await expect(form.getByText('familie.jpg',{exact:true})).toBeVisible();
 await form.getByRole('button',{name:'Anpinnen',exact:true}).click();expect(String(state.posts.at(-1))).toContain('familie.jpg');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

for(const [language,label] of [['fr','Objet existant'],['nl','Bestaand item'],['th','รายการที่มีอยู่']]){
 test(`composer root copy is localized for ${language}`,async({page})=>{await boot(page,{language});await expect(page.locator('.pin-composer').getByRole('button',{name:label,exact:true})).toBeVisible()});
}
