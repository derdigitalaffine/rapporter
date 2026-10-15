import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,{count=8,categories=4,categoryNames=null,path='/?page=shopping',beforeGoto=null}={}){
 const state=await installApiMocks(page,{dismissOnboarding:true});state.shoppingLists[0].items=Array.from({length:count},(_,index)=>({id:`density-${index}`,shopping_list:'shop-1',name:`Artikel ${index+1}`,quantity:'2×',category:categoryNames?.[index%categoryNames.length]||`Kategorie ${index%categories+1}`,aisle:'',checked:false,note:'Notiz',favorite:false,position:(index+1)*1000}));
 if(beforeGoto)await beforeGoto({page,state});
 await page.goto(path);await page.waitForLoadState('networkidle');if(!path.includes('mode=store'))await page.getByRole('button',{name:/Im Laden/}).click();await expect(page.locator('.store-focus')).toBeVisible();return state;
}

for(const config of [{count:8,categories:4},{count:12,categories:2}])test(`store · ${config.count} items in ${config.categories} categories fit at 390×844`,async({page})=>{
 await page.setViewportSize({width:390,height:844});await boot(page,config);const rows=page.locator('.store-row');await expect(rows).toHaveCount(config.count);const footer=await page.locator('.store-footer').boundingBox();for(const row of await rows.all()){const box=await row.boundingBox();expect(box.height).toBeGreaterThanOrEqual(48);expect(box.y+box.height).toBeLessThanOrEqual(footer.y+1)}await expect(page.locator('.topbar')).toBeHidden();await expect(page.locator('.global-create-fab')).toBeHidden();
});
test('store · groups follow manual walking order instead of alphabet',async({page})=>{
 await boot(page,{count:4,categories:2,categoryNames:['Zuerst','Danach']});await expect.poll(()=>page.locator('.store-group h2').allTextContents()).toEqual(['Zuerst','Danach']);
});
test('store · checked items confirm inline, leave Offen and stay recoverable without per-item toast',async({page})=>{
 const state=await boot(page);const row=page.locator('.store-row').filter({hasText:'Artikel 1'}).first();await row.locator('.store-details').click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Artikel 1',exact:true})).toBeVisible();expect(state.shoppingLists[0].items[0].checked).toBe(false);await page.keyboard.press('Escape');await row.locator('.store-check').click();await expect(row).toHaveClass(/store-completing/);await expect(row.locator('.store-check')).toHaveAttribute('aria-pressed','true');await expect(page.getByRole('button',{name:'1 im Wagen'})).toBeVisible();await expect(page.locator('.store-row')).toHaveCount(7);await expect(page.getByRole('button',{name:'Rückgängig',exact:true})).toHaveCount(0);await expect(page.locator('.toast-success')).toHaveCount(0);await page.getByRole('button',{name:/^Erledigt 1$/}).click();const doneRow=page.locator('.store-row').filter({hasText:'Artikel 1'}).first();await expect(doneRow).toHaveClass(/store-checked/);await doneRow.locator('.store-check').click();await expect(page.getByRole('button',{name:'0 im Wagen'})).toBeVisible();await expect(page.locator('.store-row')).toHaveCount(0);await page.getByRole('button',{name:/^Offen 8$/}).click();await expect(page.locator('.store-row')).toHaveCount(8);await expect.poll(()=>state.shoppingLists[0].items[0].checked).toBe(false);
});
test('store · compact header, footer add, quiet create, reload-safe list and browser Back',async({page})=>{
 const state=await boot(page,{path:'/?page=shopping&list=shop-1&mode=store'});await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.store-header').getByRole('button',{name:'Artikel hinzufügen'})).toHaveCount(0);await expect(page.locator('.store-header').getByRole('button',{name:'Liste aktualisieren'})).toHaveCount(0);await page.locator('.store-check').first().focus();await page.keyboard.press('Space');await expect(page.getByRole('button',{name:'1 im Wagen'})).toBeVisible();await expect(page.locator('.store-row')).toHaveCount(7);await page.locator('.store-footer').getByRole('button',{name:'Artikel hinzufügen'}).click();const dialog=page.getByRole('dialog');await expect(dialog.locator('input')).toBeFocused();await dialog.locator('input').fill('Vergessen');await dialog.locator('input').press('Enter');await expect(dialog).toHaveCount(0);await expect(page.getByText('Vergessen',{exact:true})).toBeVisible();await expect(page.locator('.toast-success')).toHaveCount(0);await page.reload();await expect(page.locator('.store-focus')).toBeVisible();await page.getByRole('button',{name:'Zur Planung'}).click();await expect(page.locator('.shopping-page')).toBeVisible();await page.goBack();await expect(page.locator('.store-focus')).toBeVisible();expect(state.shoppingLists[0].items.some(x=>x.name==='Vergessen')).toBe(true);
});
test('store · automatic online refresh retains local pending changes',async({page,context})=>{
 const state=await boot(page);await context.setOffline(true);await page.locator('.store-check').first().click();await expect(page.getByRole('button',{name:'1 im Wagen'})).toBeVisible();await expect(page.locator('.store-row')).toHaveCount(7);await page.getByRole('button',{name:/^Erledigt 1$/}).click();await page.locator('.store-check').first().click();await expect(page.getByRole('button',{name:'0 im Wagen'})).toBeVisible();await page.getByRole('button',{name:/^Offen 8$/}).click();await expect(page.locator('.store-row')).toHaveCount(8);state.shoppingLists[0].items.push({id:'remote-item',name:'Von Zuhause',checked:false,category:'Kategorie 1',shopping_list:'shop-1',position:9000});await context.setOffline(false);await expect(page.getByText('Von Zuhause',{exact:true})).toBeVisible();await expect.poll(()=>state.shoppingLists[0].items[0].checked).toBe(false);
});
test('store · remote add and check arrive through live session cursor without full refresh',async({page})=>{
 let sessionPolls=0;let fullListReads=0;
 page.on('request',request=>{const url=new URL(request.url());if(request.method()==='GET'&&url.pathname==='/api/shopping-lists/')fullListReads+=1});
 const session={id:'session-1',shopping_list:'shop-1',status:'active',started_at:new Date().toISOString(),last_activity_at:new Date().toISOString(),started_by:{id:1,name:'Alex',avatar:'',is_self:true},participants:[{id:1,name:'Alex',avatar:'',is_self:true},{id:2,name:'Sam',avatar:'S',is_self:false}]};
 await boot(page,{count:8,categories:2,beforeGoto:async({page})=>{
  await page.route('**/api/shopping-sessions/start/',route=>route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({session,cursor:0,activities:[],created:true})}));
  await page.route('**/api/shopping-sessions/current/**',route=>{
   sessionPolls+=1;
   const remoteItem={id:'remote-live',shopping_list:'shop-1',name:'Von Sam',quantity:'1×',category:'Kategorie 1',aisle:'',note:'',favorite:false,checked:false,checked_at:null,position:8500};
   const checkedItem={id:'density-0',shopping_list:'shop-1',name:'Artikel 1',quantity:'2×',category:'Kategorie 1',aisle:'',note:'Notiz',favorite:false,checked:true,checked_at:new Date().toISOString(),position:1000};
   const activities=sessionPolls===1?[{sequence:1,kind:'item_added',item_id:remoteItem.id,item_name:remoteItem.name,actor:{id:2,name:'Sam',avatar:'S',is_self:false},item:remoteItem,created_at:new Date().toISOString()}]:sessionPolls===2?[{sequence:2,kind:'item_checked',item_id:checkedItem.id,item_name:checkedItem.name,actor:{id:2,name:'Sam',avatar:'S',is_self:false},item:checkedItem,created_at:new Date().toISOString()}]:[];
   const cursor=sessionPolls===1?1:2;
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session,cursor,activities})});
  });
 }});
 const initialFullReads=fullListReads;
 await expect(page.getByText('Einkauf läuft',{exact:true})).toBeVisible();await expect(page.getByText('Gemeinsam mit Sam',{exact:true})).toBeVisible();
 await expect(page.getByText('Von Sam',{exact:true})).toBeVisible({timeout:6000});await expect(page.getByText('Sam hat Von Sam ergänzt',{exact:true})).toBeVisible();
 await expect(page.getByText('Artikel 1',{exact:true})).toHaveCount(0,{timeout:6000});await expect(page.getByText('Sam hat Artikel 1 abgehakt',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'1 im Wagen'})).toBeVisible();
 expect(sessionPolls).toBeGreaterThanOrEqual(2);expect(fullListReads).toBe(initialFullReads);
});