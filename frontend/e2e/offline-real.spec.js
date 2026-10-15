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
test('Shopping survives real network loss and reload, then converges once to PostgreSQL',async({page,context})=>{
 const family=await boot(page);await context.setOffline(true);
 const name=`Offline bread ${Date.now()}`;const input=page.locator('.smart-input input');await input.fill(name);await input.press('Enter');await expect(page.getByText(name,{exact:true})).toBeVisible();
 await page.reload();await expect(page.getByText(name,{exact:true})).toBeVisible();
 await context.setOffline(false);
 await expect.poll(async()=>{const response=await page.request.get(`/api/shopping-lists/?family=${family.id}`);const value=await response.json();return (value.results||value).flatMap(list=>list.items).filter(item=>item.name===name).length},{timeout:20000}).toBe(1);
 await expect(page.locator('.offline-sync-primary')).toHaveText('Synced',{timeout:20000});
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
 await expect(page.locator('.offline-sync-primary')).toHaveText('Synced',{timeout:20000});
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
 await expect(page.locator('.offline-sync-primary')).toHaveText('Synced',{timeout:20000});
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
 await expect(page.locator('.offline-sync-primary')).toHaveText('Synced',{timeout:20000});
 const response=await page.request.post('/api/sync/',{data:{protocol_version:999,family_id:family.id,cursor:0,mutations:[]}});expect(response.status()).toBe(409);
});

test('server failure remains visible with browser online; status sheet is responsive and keyboard accessible',async({page},testInfo)=>{
 await boot(page);const primary=page.locator('.offline-sync-primary'),pill=page.locator('.offline-sync-pill');
 await expect(primary).toHaveText('Synced',{timeout:20000});
 await page.route('**/api/sync/',route=>route.abort('connectionrefused'));
 await page.evaluate(()=>window.dispatchEvent(new CustomEvent('familyos:sync-now')));
 expect(await page.evaluate(()=>navigator.onLine)).toBeTruthy();await expect(primary).toHaveText('Server unavailable');
 for(const width of [320,390,1440]){
  await page.setViewportSize({width,height:844});await pill.click();const dialog=page.getByRole('dialog',{name:'Synchronization',exact:true});await expect(dialog).toBeVisible();
  await expect(dialog.getByText('Last successful sync',{exact:true})).toBeVisible();await expect(dialog.locator('time')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const screenshotPath=testInfo.outputPath(`sync-status-${width}.png`);
  await page.screenshot({path:screenshotPath});await testInfo.attach(`sync-status-${width}`,{path:screenshotPath,contentType:'image/png'});
  await page.keyboard.press('Escape');await expect(dialog).toBeHidden();await expect(pill).toBeFocused();
 }
 await page.unroute('**/api/sync/');await page.evaluate(()=>window.dispatchEvent(new CustomEvent('familyos:sync-now')));await expect(primary).toHaveText('Synced',{timeout:20000});
});

test('family subscription uses one Calendar/Settings flow with permanent link, additional profile and revocation',async({page},testInfo)=>{
 const family=await boot(page);await page.goto('/?page=calendar&view=list');
 await page.getByRole('button',{name:'Subscribe to calendar',exact:true}).click();
 let dialog=page.getByRole('dialog',{name:'Calendar subscriptions',exact:true});await expect(dialog).toBeVisible();
 await dialog.getByLabel('Device or subscription name',{exact:true}).fill('Test iPhone');
 await dialog.getByRole('button',{name:'Create subscription link',exact:true}).click();
 let link=dialog.getByLabel('Permanent subscription link',{exact:true});await expect(link).toBeVisible();const url=await link.inputValue();
 expect(url).toMatch(/^https:\/\/calendar\.example\.test\/calendar-feed\/[A-Za-z0-9_-]{43}\/family\.ics$/);
 await expect(dialog.getByText(/Anyone with the link can read/)).toBeVisible();
 await expect(dialog.getByRole('button',{name:'Download iPhone profile',exact:true})).toBeVisible();
 const id=(await (await page.request.get(`/api/calendar-subscriptions/${family.id}/`)).json()).subscriptions.find(row=>row.name==='Test iPhone').id;
 const path=new URL(url).pathname;
 try{
  expect((await page.request.get(path)).status()).toBe(200);
  const profileDownload=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download iPhone profile',exact:true}).click();const download=await profileDownload;expect(download.suggestedFilename()).toBe('familyos-calendar.mobileconfig');
  await expect(dialog.getByText(/Downloading does not mean it is installed/)).toBeVisible();
  for(const width of [320,390,1440]){
   await page.setViewportSize({width,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
   const screenshotPath=testInfo.outputPath(`calendar-subscriptions-${width}.png`);await page.screenshot({path:screenshotPath,mask:[link]});await testInfo.attach(`calendar-subscriptions-${width}`,{path:screenshotPath,contentType:'image/png'});
  }
  await page.keyboard.press('Escape');await expect(dialog).toBeHidden();
  await page.goto('/?page=settings');await page.getByRole('button',{name:'Subscribe to calendar',exact:true}).click();
  dialog=page.getByRole('dialog',{name:'Calendar subscriptions',exact:true});await expect(dialog.getByText('Test iPhone',{exact:true})).toBeVisible();
  await expect(dialog.getByLabel('Permanent subscription link',{exact:true})).toHaveCount(0);
  await dialog.getByRole('button',{name:'Show link',exact:true}).click();await expect(dialog.getByLabel('Permanent subscription link',{exact:true})).toHaveValue(url);
  await dialog.getByRole('button',{name:'Revoke link',exact:true}).click();const confirmation=page.getByRole('alertdialog');await expect(confirmation).toBeVisible();await confirmation.getByRole('button',{name:'Revoke link',exact:true}).click();
  await expect(dialog.getByText('Test iPhone',{exact:true})).toHaveCount(0);expect((await page.request.get(path)).status()).toBe(404);
 }finally{await page.request.delete(`/api/calendar-subscriptions/${family.id}/${id}/`)}
});
