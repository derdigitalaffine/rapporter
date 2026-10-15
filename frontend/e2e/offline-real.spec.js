import {test,expect} from '@playwright/test';
// These tests intentionally use a real PostgreSQL/Django API. The ordinary E2E
// matrix uses mock-api.js; this separate config is the actual offline gate.
test.skip(!process.env.OFFLINE_E2E,'Run through playwright.offline.config.js with a seeded real backend');
async function boot(page){
 const response=await page.request.post('/api/auth/login/',{data:{username:'offline-e2e',password:'offline-e2e-only-password',legacy:true}});expect(response.ok()).toBeTruthy();
 await page.addInitScript(()=>{localStorage.setItem('famuhle-session','1');localStorage.setItem('famuhle-language','en')});
 await page.goto('/?page=shopping');
 await expect(page.getByText('Offline milk',{exact:true})).toBeVisible();
 const data=await page.request.get('/api/families/');const families=await data.json();const family=(families.results||families)[0];
 await page.evaluate(id=>localStorage.setItem(`famuhle-onboarding-dismissed:${id}`,'1'),family.id);
 await page.evaluate(async()=>{await navigator.serviceWorker.ready;if(!navigator.serviceWorker.controller)await new Promise(resolve=>navigator.serviceWorker.addEventListener('controllerchange',resolve,{once:true}))});
 return family;
}
async function expectConfirmed(page){
 const pill=page.locator('.offline-sync-pill');await pill.click();
 const dialog=page.getByRole('dialog',{name:'Synchronization',exact:true});
 await expect(dialog.locator('.offline-sync-summary')).toHaveText('Synced',{timeout:20000});
 await expect(dialog.locator('time')).toBeVisible();
 await dialog.getByRole('button',{name:'Close',exact:true}).click();
}
test('Shopping survives real network loss and reload, then converges once to PostgreSQL',async({page,context})=>{
 const family=await boot(page);await context.setOffline(true);
 const name=`Offline bread ${Date.now()}`;const input=page.locator('.smart-input input');await input.fill(name);await input.press('Enter');await expect(page.getByText(name,{exact:true})).toBeVisible();
 await page.reload();await expect(page.getByText(name,{exact:true})).toBeVisible();
 await context.setOffline(false);
 await expect.poll(async()=>{const response=await page.request.get(`/api/shopping-lists/?family=${family.id}`);const value=await response.json();return (value.results||value).flatMap(list=>list.items).filter(item=>item.name===name).length},{timeout:20000}).toBe(1);
 await expectConfirmed(page);
});
test('Explicit logout clears account-private normalized entities and outbox',async({page})=>{
 await boot(page);await page.locator('.bottom-nav').getByRole('button',{name:'More',exact:true}).click();await page.getByRole('button',{name:'Sign out',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>localStorage.getItem('familyos-offline-account'))).toBeNull();
 expect(await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('familyos-local-sync');r.onsuccess=()=>{const db=r.result,tx=db.transaction('outbox','readonly'),read=tx.objectStore('outbox').getAll();read.onsuccess=()=>resolve(read.result.length);tx.oncomplete=()=>db.close()};r.onerror=()=>reject(r.error)}))).toBe(0);
});
test('Tasks create, complete and reopen offline, retaining commands through reload',async({page,context})=>{
 const family=await boot(page);await page.goto('/?page=tasks');await expect(page.getByText('Offline task',{exact:true})).toBeVisible();await context.setOffline(true);
 const title=`Offline task ${Date.now()}`;const input=page.locator('.smart-input input');await input.fill(title);await input.press('Enter');
 const row=page.locator('.smart-row').filter({hasText:title});await expect(row).toBeVisible();await row.locator('.smart-check').click();
 await page.getByRole('button',{name:'Show completed',exact:true}).click();await expect(row.locator('.smart-check')).toHaveClass(/checked/);
 await page.reload();await page.getByRole('button',{name:'Show completed',exact:true}).click();await expect(row.locator('.smart-check')).toHaveClass(/checked/);await row.locator('.smart-check').click();
 await context.setOffline(false);await expect.poll(async()=>{const response=await page.request.get(`/api/tasks/?family=${family.id}`);const value=await response.json();return (value.results||value).filter(t=>t.title===title&&t.completed_at===null).length},{timeout:20000}).toBe(1);
 await expectConfirmed(page);
});
test('Calendar native creation survives offline reload and external events remain read-only',async({page,context})=>{
 const family=await boot(page);await page.goto('/?page=calendar&view=list');
 await expect(page.getByText('Read-only external',{exact:true})).toBeVisible();await context.setOffline(true);
 await page.locator('.global-create-fab').click();
 let dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
 let titleInput=dialog.getByRole('textbox',{name:'Title',exact:true});
 if(!await titleInput.count()){
   let eventChoice=dialog.getByRole('button',{name:/^Event(?:\s|$)/});
   if(!await eventChoice.count()){
     const allActions=dialog.getByRole('button',{name:'All actions',exact:true});
     if(await allActions.count())await allActions.click();
     eventChoice=dialog.getByRole('button',{name:/^Event(?:\s|$)/});
   }
   await expect(eventChoice.first()).toBeVisible();await eventChoice.first().click();
   dialog=page.getByRole('dialog');titleInput=dialog.getByRole('textbox',{name:'Title',exact:true});
 }
 const title=`Offline event ${Date.now()}`,editor=dialog;await expect(titleInput).toBeVisible();await titleInput.fill(title);await editor.getByRole('button',{name:'Save',exact:true}).click();await expect(editor).toBeHidden();
 await expect(page.getByText(title,{exact:true})).toBeVisible();await page.reload();await expect(page.getByText(title,{exact:true})).toBeVisible();
 await page.getByText('Read-only external',{exact:true}).click();const detail=page.getByRole('dialog');await expect(detail.getByRole('button',{name:'Edit event',exact:true})).toHaveCount(0);await detail.locator('.sheet-close').click();
 await context.setOffline(false);await expect.poll(async()=>{const response=await page.request.get(`/api/events/?family=${family.id}&birthdays=0`);const value=await response.json();return (value.results||value).filter(event=>event.title===title).length},{timeout:20000}).toBe(1);
 await expectConfirmed(page);
});

test('two independent clients merge disjoint edits, preserve field conflicts and propagate deletion',async({page,browser})=>{
 const family=await boot(page),other=await browser.newContext({baseURL:'http://127.0.0.1:4173'});
 try{
  const login=await other.request.post('/api/auth/login/',{data:{username:'offline-e2e',password:'offline-e2e-only-password',legacy:true}});expect(login.ok()).toBeTruthy();
  const sync=async(client,mutations=[],cursor=null)=>{const response=await client.post('/api/sync/',{data:{protocol_version:1,family_id:family.id,cursor,mutations}});expect(response.ok()).toBeTruthy();return response.json()};
  const seed=await sync(page.request),id=crypto.randomUUID();
  const created=await sync(page.request,[{mutation_id:crypto.randomUUID(),entity_type:'shopping_item',entity_id:id,operation:'create',base_version:null,data:{shopping_list:seed.snapshot.shopping_lists[0].id,name:'Concurrent case'}}]);expect(created.mutation_results[0].status).toBe('applied');
  const initial=await sync(page.request),item=initial.snapshot.shopping_items.find(row=>row.id===id);
  const mutation=(changes,version=item.version,operation='update')=>({mutation_id:crypto.randomUUID(),entity_type:'shopping_item',entity_id:item.id,operation,base_version:version,changes});
  const first=await sync(page.request,[mutation({quantity:'3'})],initial.cursor);expect(first.mutation_results[0].status).toBe('applied');
  const second=await sync(other.request,[mutation({note:'Second client'})],initial.cursor);expect(second.mutation_results[0].status).toBe('applied');
  const lost=mutation({quantity:'4'},second.mutation_results[0].version);
  expect((await sync(page.request,[lost],second.cursor)).mutation_results[0].status).toBe('applied');
  expect((await sync(page.request,[lost],second.cursor)).mutation_results[0].status).toBe('already_applied');
  const conflict=await sync(other.request,[mutation({quantity:'5'})],initial.cursor);expect(conflict.mutation_results[0].status).toBe('conflict');expect(conflict.mutation_results[0].conflicts.quantity.client).toBe('5');expect(conflict.mutation_results[0].conflicts.quantity.server).toBe('4');
  const latest=await sync(page.request),version=latest.snapshot.shopping_items.find(row=>row.id===item.id).version;
  expect((await sync(page.request,[mutation({},version,'delete')],latest.cursor)).mutation_results[0].status).toBe('applied');
  const deleted=await sync(other.request,[],latest.cursor);expect(deleted.visibility.shopping_item).not.toContain(item.id);expect(deleted.cursor).toBeGreaterThan(latest.cursor);expect(deleted.changes.some(row=>row.entity_id===item.id)).toBeFalsy();
 }finally{await other.close()}
});


test('snapshot reset preserves pending offline create and unsupported protocol cannot write',async({page,context})=>{
 const family=await boot(page);await context.setOffline(true);
 const name=`Snapshot draft ${Date.now()}`;const input=page.locator('.smart-input input');await input.fill(name);await input.press('Enter');await expect(page.getByText(name,{exact:true})).toBeVisible();
 await page.evaluate(async familyId=>{
  await new Promise((resolve,reject)=>{const request=indexedDB.open('familyos-local-sync');request.onerror=()=>reject(request.error);request.onsuccess=()=>{const db=request.result,tx=db.transaction('syncState','readwrite'),store=tx.objectStore('syncState');const rows=store.getAll();rows.onsuccess=()=>{for(const row of rows.result)if(row.familyId===familyId)store.put({...row,cursor:Number.MAX_SAFE_INTEGER})};tx.oncomplete=()=>{db.close();resolve()};tx.onabort=()=>reject(tx.error)}});
 },String(family.id));
 await page.reload();await expect(page.getByText(name,{exact:true})).toBeVisible();await context.setOffline(false);
 await expect.poll(async()=>{const response=await page.request.get(`/api/shopping-lists/?family=${family.id}`);const value=await response.json();return (value.results||value).flatMap(list=>list.items).filter(item=>item.name===name).length},{timeout:20000}).toBe(1);
 await expectConfirmed(page);
 const response=await page.request.post('/api/sync/',{data:{protocol_version:999,family_id:family.id,cursor:0,mutations:[]}});expect(response.status()).toBe(409);
});

test('server failure remains visible with browser online; status sheet is responsive and keyboard accessible',async({page},testInfo)=>{
 await boot(page);const pill=page.locator('.offline-sync-pill'),led=pill.locator('.offline-sync-led');
 await expectConfirmed(page);await expect(pill.locator('.offline-sync-label')).toHaveText('Sync');
 await page.route('**/api/sync/',route=>route.abort('connectionrefused'));
 await page.evaluate(()=>window.dispatchEvent(new CustomEvent('familyos:sync-now')));
 expect(await page.evaluate(()=>navigator.onLine)).toBeTruthy();await expect(led).toHaveAttribute('data-tone','error');await expect(pill.locator('.offline-sync-label')).toHaveText('Sync');
 for(const width of [320,390,1440]){
  await page.setViewportSize({width,height:844});await pill.click();const dialog=page.getByRole('dialog',{name:'Synchronization',exact:true});await expect(dialog).toBeVisible();
  await expect(dialog.locator('.offline-sync-summary')).toHaveText('Server unavailable');
  await expect(dialog.getByText('Last successful sync',{exact:true})).toBeVisible();await expect(dialog.locator('time')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const screenshotPath=testInfo.outputPath(`sync-status-${width}.png`);
  await page.screenshot({path:screenshotPath});await testInfo.attach(`sync-status-${width}`,{path:screenshotPath,contentType:'image/png'});
  await page.keyboard.press('Escape');await expect(dialog).toBeHidden();await expect(pill).toBeFocused();
 }
 await page.unroute('**/api/sync/');await page.evaluate(()=>window.dispatchEvent(new CustomEvent('familyos:sync-now')));await expectConfirmed(page);
});


test('quiet header LED and label stay steady through repeated routine syncs',async({page},testInfo)=>{
 await boot(page);await expectConfirmed(page);
 const pill=page.locator('.offline-sync-pill'),led=pill.locator('.offline-sync-led');
 const initialTone=await led.getAttribute('data-tone');
 await page.route('**/api/sync/',async route=>{await new Promise(resolve=>setTimeout(resolve,900));await route.continue()});
 await page.evaluate(()=>{
  const pill=document.querySelector('.offline-sync-pill');window.__syncIndicatorSamples=[];
  window.__syncIndicatorObserver=new MutationObserver(()=>window.__syncIndicatorSamples.push({label:pill.querySelector('.offline-sync-label').textContent,tone:pill.querySelector('.offline-sync-led').dataset.tone}));
  window.__syncIndicatorObserver.observe(pill,{subtree:true,childList:true,characterData:true,attributes:true});
 });
 for(let i=0;i<3;i++){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/sync/')&&r.request().method()==='POST');
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('familyos:sync-now')));
  await expect(pill.locator('.offline-sync-label')).toHaveText('Sync');await expect(led).toHaveAttribute('data-tone',initialTone);
  expect((await response).ok()).toBeTruthy();
  // The response arrives before IndexedDB reconciliation clears engine.inflight.
  // Wait for the completed UI state before requesting the next distinct sync.
  await expectConfirmed(page);await expect(led).toHaveAttribute('data-tone',initialTone);
 }
 const samples=await page.evaluate(()=>{window.__syncIndicatorObserver.disconnect();return window.__syncIndicatorSamples});
 expect(samples.every(row=>row.label==='Sync'&&row.tone===initialTone)).toBeTruthy();
 await page.unroute('**/api/sync/');
 const screenshotPath=testInfo.outputPath('sync-status-quiet-led.png');await page.screenshot({path:screenshotPath});await testInfo.attach('sync-status-quiet-led',{path:screenshotPath,contentType:'image/png'});
 await pill.click();const dialog=page.getByRole('dialog',{name:'Synchronization',exact:true});
 await dialog.locator('.offline-sync-legend summary').click();await expect(dialog.getByText('Up to date and live connected',{exact:true})).toBeVisible();
 await page.keyboard.press('Escape');await expect(pill).toBeFocused();
});
