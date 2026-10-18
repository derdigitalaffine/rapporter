import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

async function installTemplateMocks(page,state){
 const stores=[];const templates=[];
 let seq=1;
 const syncStoreLabels=store=>{for(const list of state.shoppingLists){if((store.shopping_list_ids||[]).some(id=>String(id)===String(list.id)))list.store=store.display_label}};
 await page.route('**/api/**',async route=>{
  const request=route.request();const method=request.method();const url=new URL(request.url());const path=url.pathname.replace(/^\/api/,'');let body={};try{body=request.postDataJSON()||{}}catch{}
  if(path==='/shopping-stores/'&&method==='GET')return json(route,stores);
  if(path==='/shopping-stores/'&&method==='POST'){
   const row={id:`store-${seq++}`,family:body.family,name:body.name,branch_label:body.branch_label||'',display_label:body.branch_label?`${body.name} · ${body.branch_label}`:body.name,address:body.address||'',website_url:body.website_url||'',offers_url:body.offers_url||'',note:body.note||'',active:true,sort_order:body.sort_order||0,shopping_list_ids:[]};stores.push(row);return json(route,row,201);
  }
  let match=path.match(/^\/shopping-stores\/([^/]+)\/$/);
  if(match&&method==='PATCH'){
   const store=stores.find(row=>row.id===match[1]);Object.assign(store,body);store.display_label=store.branch_label?`${store.name} · ${store.branch_label}`:store.name;syncStoreLabels(store);return json(route,store);
  }
  if(match&&method==='DELETE'){
   const index=stores.findIndex(row=>row.id===match[1]);const store=stores[index];const referenced=(store?.shopping_list_ids||[]).length||templates.some(template=>String(template.default_store)===String(store?.id));
   if(referenced)return json(route,{detail:'Dieser Einkaufsort wird noch von einer Einkaufsliste oder Vorlage verwendet. Deaktiviere ihn stattdessen oder entferne zuerst die Zuordnungen.'},409);
   stores.splice(index,1);return route.fulfill({status:204,body:''});
  }
  match=path.match(/^\/shopping-stores\/([^/]+)\/assign\/$/);
  if(match&&method==='POST'){
   const store=stores.find(row=>row.id===match[1]);for(const row of stores)row.shopping_list_ids=(row.shopping_list_ids||[]).filter(id=>String(id)!==String(body.shopping_list));store.shopping_list_ids=[...(store.shopping_list_ids||[]),body.shopping_list];const list=state.shoppingLists.find(row=>row.id===body.shopping_list);if(list)list.store=store.display_label;return json(route,{shopping_list:body.shopping_list,store:store.id,display_label:store.display_label});
  }
  if(path==='/shopping-templates/'&&method==='GET')return json(route,templates);
  if(path==='/shopping-templates/'&&method==='POST'){
   const store=stores.find(row=>row.id===body.default_store);const row={id:`template-${seq++}`,family:body.family,name:body.name,description:body.description||'',default_store:body.default_store||null,default_store_label:store?.display_label||'',archived:false,sort_order:0,items:(body.items||[]).map((item,index)=>({id:`tpl-item-${seq++}`,name:item.name,quantity:item.quantity||'',category:item.category||'',aisle:item.aisle||'',note:item.note||'',position:item.position??index})),item_count:(body.items||[]).length};templates.push(row);return json(route,row,201);
  }
  if(path==='/shopping-templates/from-list/'&&method==='POST'){
   const list=state.shoppingLists.find(row=>row.id===body.shopping_list);const selected=new Set(body.item_ids||[]);const rows=(list?.items||[]).filter(item=>!selected.size||selected.has(item.id));const store=stores.find(row=>row.id===body.default_store);const row={id:`template-${seq++}`,family:list.family,name:body.name||list.name,description:'',default_store:body.default_store||null,default_store_label:store?.display_label||'',archived:false,sort_order:0,items:rows.map((item,index)=>({id:`tpl-item-${seq++}`,name:item.name,quantity:item.quantity||'',category:item.category||'',aisle:item.aisle||'',note:item.note||'',position:index})),item_count:rows.length};templates.push(row);return json(route,row,201);
  }
  match=path.match(/^\/shopping-templates\/([^/]+)\/preview\/$/);
  if(match&&method==='GET'){
   const template=templates.find(row=>row.id===match[1]);const list=state.shoppingLists.find(row=>row.id===url.searchParams.get('shopping_list'));let created=0,reopened=0,already_open=0;
   for(const item of template.items){const same=(list.items||[]).filter(row=>row.name.trim().toLocaleLowerCase()===item.name.trim().toLocaleLowerCase());if(same.some(row=>!row.checked))already_open++;else if(same.some(row=>row.checked))reopened++;else created++}
   return json(route,{created,reopened,already_open,total:created+reopened+already_open});
  }
  match=path.match(/^\/shopping-templates\/([^/]+)\/apply\/$/);
  if(match&&method==='POST'){
   const template=templates.find(row=>row.id===match[1]);const list=state.shoppingLists.find(row=>row.id===body.shopping_list);let created=0,reopened=0,already_open=0;
   for(const item of template.items){const same=(list.items||[]).filter(row=>row.name.trim().toLocaleLowerCase()===item.name.trim().toLocaleLowerCase());const open=same.find(row=>!row.checked);if(open){already_open++;continue}const checked=same.find(row=>row.checked);if(checked){checked.checked=false;checked.quantity=checked.quantity||item.quantity;reopened++;continue}list.items.push({id:`item-${seq++}`,shopping_list:list.id,name:item.name,quantity:item.quantity,category:item.category,aisle:item.aisle,note:item.note,favorite:false,checked:false,added_by_name:'Alex'});created++}
   return json(route,{created,reopened,already_open,total:created+reopened+already_open});
  }
  match=path.match(/^\/shopping-templates\/([^/]+)\/create-list\/$/);
  if(match&&method==='POST'){
   const template=templates.find(row=>row.id===match[1]);const row={id:`shop-${seq++}`,family:'family-1',name:body.name||template.name,store:template.default_store_label||'',icon:'cart-shopping',archived:false,sort_order:0,items:template.items.map(item=>({id:`item-${seq++}`,shopping_list:'new',name:item.name,quantity:item.quantity,category:item.category,aisle:item.aisle,note:item.note,favorite:false,checked:false,added_by_name:'Alex'}))};state.shoppingLists.push(row);return json(route,row,201);
  }
  return route.fallback();
 });
 return {stores,templates};
}

async function openTools(page){
 await page.goto('/?page=shopping');
 const planningButton=page.locator('.shopping-list-switcher').getByRole('button',{name:'Vorlagen'});
 await expect(planningButton).toBeVisible();
 await planningButton.click();
 await expect(page.getByTestId('shopping-template-tools')).toBeVisible();
}
async function waitForOfflineShell(page){
 await page.evaluate(async()=>{
  if(!('serviceWorker' in navigator))throw new Error('service_worker_unavailable');
  await navigator.serviceWorker.ready;
  if(!navigator.serviceWorker.controller){
   await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('service_worker_controller_timeout')),6000);navigator.serviceWorker.addEventListener('controllerchange',()=>{clearTimeout(timeout);resolve()},{once:true})});
  }
 });
}

test('templates are discoverable from the shopping flow and the empty state',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});state.shoppingLists[0].items=[];await installTemplateMocks(page,state);
 await page.goto('/?page=shopping');
 await expect(page.getByRole('button',{name:'Vorlage verwenden'})).toBeVisible();
 await page.getByRole('button',{name:'Vorlage verwenden'}).click();
 await expect(page.getByRole('heading',{name:'Vorlagen & Einkaufsorte',level:2})).toBeVisible();
 await expect(page.getByTestId('shopping-template-tools')).toBeVisible();
});

test('shopping list can be saved as template, previewed and applied without duplicates',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.shoppingLists[0].items.push({id:'item-checked',shopping_list:'shop-1',name:'Brot',quantity:'1',category:'Backwaren',aisle:'',note:'',favorite:false,checked:true,added_by_name:'Alex'});
 const apiState=await installTemplateMocks(page,state);
 await openTools(page);
 const tools=page.getByTestId('shopping-template-tools');
 const saveForm=tools.locator('.template-inline-form').filter({hasText:'Aktuelle Liste als Vorlage speichern'});
 await saveForm.locator('input').fill('Wocheneinkauf');
 await saveForm.getByRole('button',{name:'Vorlage speichern'}).click();
 await expect(tools.getByText('Wocheneinkauf',{exact:true})).toBeVisible();
 expect(apiState.templates).toHaveLength(1);
 await tools.getByRole('button',{name:'Vorschau'}).click();
 await expect(tools.getByText(/0 neu · 1 wieder öffnen · 1 bereits offen/)).toBeVisible();
 await tools.getByRole('button',{name:'Vorlage verwenden'}).click();
 await expect(page.getByText('Brot',{exact:true})).toBeVisible();
 expect(state.shoppingLists[0].items.filter(item=>item.name==='Milch'&&!item.checked)).toHaveLength(1);
 expect(state.shoppingLists[0].items.find(item=>item.id==='item-checked').checked).toBe(false);
});

test('shopping place assigns legacy display label and exposes safe offers link in store mode',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});await installTemplateMocks(page,state);await openTools(page);
 const tools=page.getByTestId('shopping-template-tools');
 await tools.getByRole('button',{name:'Neuer Einkaufsort'}).click();
 const storeForm=tools.locator('form').filter({hasText:'Standort / Filialzusatz (optional)'});
 await storeForm.getByLabel('Name des Einkaufsorts').fill('REWE');
 await storeForm.getByLabel('Standort / Filialzusatz (optional)').fill('Innenstadt');
 await storeForm.getByLabel('Wochenangebot (HTTPS)').fill('https://offers.example.test/rewe');
 await storeForm.getByRole('button',{name:'Speichern'}).click();
 await tools.getByLabel('Einkaufsort für diese Liste').selectOption({label:'REWE · Innenstadt'});
 await tools.getByRole('button',{name:'Zuordnen'}).click();
 await expect(page.locator('.shopping-session-title small')).toContainText('REWE · Innenstadt');
 await page.locator('.family-sheet .sheet-close').click();
 await expect(tools).not.toBeVisible();
 await page.locator('.shopping-store-entry').click();
 const offers=page.getByRole('link',{name:'Angebote ansehen'});
 await expect(offers).toHaveAttribute('href','https://offers.example.test/rewe');
 await expect(offers).toHaveAttribute('target','_blank');
 await expect(offers).toHaveAttribute('rel',/noopener/);
});

test('shopping places can be edited, deactivated and only deleted when unreferenced',async({page})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});const apiState=await installTemplateMocks(page,state);await openTools(page);
 const tools=page.getByTestId('shopping-template-tools');
 await tools.getByRole('button',{name:'Neuer Einkaufsort'}).click();
 let form=tools.locator('form').filter({hasText:'Standort / Filialzusatz (optional)'});
 await form.getByLabel('Name des Einkaufsorts').fill('REWE');
 await form.getByLabel('Adresse (optional)').fill('Marktstraße 1');
 await form.getByRole('button',{name:'Speichern'}).click();

 let card=tools.locator('.template-card').filter({hasText:'REWE'});
 await card.getByRole('button',{name:'Bearbeiten'}).click();
 form=tools.locator('form').filter({hasText:'Standort / Filialzusatz (optional)'});
 await form.getByLabel('Standort / Filialzusatz (optional)').fill('West');
 await form.getByLabel('Notiz (optional)').fill('Parkhaus hinten');
 await form.getByRole('button',{name:'Speichern'}).click();
 card=tools.locator('.template-card').filter({hasText:'REWE · West'});
 await expect(card).toContainText('Marktstraße 1');

 await card.getByRole('button',{name:'Deaktivieren'}).click();
 await expect(card).toContainText('Inaktiv');
 await card.getByRole('button',{name:'Reaktivieren'}).click();
 await expect(card.getByRole('button',{name:'Deaktivieren'})).toBeVisible();

 await tools.getByLabel('Einkaufsort für diese Liste').selectOption({label:'REWE · West'});
 await tools.getByRole('button',{name:'Zuordnen'}).click();
 await card.getByRole('button',{name:'Löschen'}).click();
 await page.getByRole('button',{name:'Löschen',exact:true}).last().click();
 await expect(tools.getByRole('alert')).toContainText('noch von einer Einkaufsliste oder Vorlage verwendet');
 expect(apiState.stores).toHaveLength(1);

 await tools.getByRole('button',{name:'Neuer Einkaufsort'}).click();
 form=tools.locator('form').filter({hasText:'Standort / Filialzusatz (optional)'});
 await form.getByLabel('Name des Einkaufsorts').fill('Wochenmarkt');
 await form.getByRole('button',{name:'Speichern'}).click();
 const market=tools.locator('.template-card').filter({hasText:'Wochenmarkt'});
 await market.getByRole('button',{name:'Löschen'}).click();
 await page.getByRole('button',{name:'Löschen',exact:true}).last().click();
 await expect(market).toHaveCount(0);
 expect(apiState.stores).toHaveLength(1);
});

test('loaded template can be queued offline and is applied once after reconnect',async({page,context})=>{
 const state=await installApiMocks(page,{dismissOnboarding:true});await installTemplateMocks(page,state);await openTools(page);
 const tools=page.getByTestId('shopping-template-tools');
 await tools.getByRole('button',{name:'Neue Vorlage'}).click();
 const form=tools.locator('form').filter({hasText:'Artikel – einer pro Zeile'});
 await form.getByLabel('Name der Vorlage').fill('Offline-Vorrat');
 await form.getByLabel('Artikel – einer pro Zeile').fill('Brot offline');
 await form.getByRole('button',{name:'Vorlage speichern'}).click();
 await expect(tools.getByText('Offline-Vorrat',{exact:true})).toBeVisible();
 await waitForOfflineShell(page);await context.setOffline(true);
 await expect(tools.getByText(/Geladene Vorlagen bleiben offline verfügbar/)).toBeVisible();
 await tools.getByRole('button',{name:'Vorlage verwenden'}).click();
 await tools.getByRole('button',{name:'Vorlage verwenden'}).click();
 await expect(page.getByText(/Vorlage vorgemerkt/)).toHaveCount(1);
 expect(state.shoppingLists[0].items.some(item=>item.name==='Brot offline')).toBe(false);
 await context.setOffline(false);
 await expect.poll(()=>state.shoppingLists[0].items.filter(item=>item.name==='Brot offline').length,{timeout:10000}).toBe(1);
});

test('manual template and planning tools stay usable in English at 390px',async({page})=>{
 await page.setViewportSize({width:390,height:844});const state=await installApiMocks(page,{language:'en',dismissOnboarding:true});await installTemplateMocks(page,state);
 await page.goto('/?page=shopping');
 await page.locator('.shopping-list-switcher').getByRole('button',{name:'Templates'}).click();
 const tools=page.getByTestId('shopping-template-tools');
 await expect(tools.getByRole('heading',{name:'Templates & shopping places'})).toBeVisible();
 await tools.getByRole('button',{name:'New template'}).click();
 const form=tools.locator('form').filter({hasText:'Items — one per line'});
 await form.getByLabel('Template name').fill('Breakfast');
 await form.getByLabel('Items — one per line').fill('Coffee\nBread\nMilk');
 await form.getByRole('button',{name:'Save template'}).click();
 await expect(tools.getByText('Breakfast',{exact:true})).toBeVisible();
 const overflowWidth=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflowWidth).toBeLessThanOrEqual(0);
});
