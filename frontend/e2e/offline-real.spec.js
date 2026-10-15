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
 await expect(page.locator('.offline-sync-pill')).toHaveText('Synced',{timeout:20000});
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
 await expect(page.locator('.offline-sync-pill')).toHaveText('Synced',{timeout:20000});
});
test('Calendar native creation survives offline reload and external events remain read-only',async({page,context})=>{
 const family=await boot(page);await page.goto('/?page=calendar&view=list');
 await expect(page.getByText('Read-only external',{exact:true})).toBeVisible();await context.setOffline(true);
 await page.locator('.global-create-fab').click();
 let dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
 let titleInput=dialog.getByLabel('Title',{exact:true});
 if(!await titleInput.count()){
   let eventChoice=dialog.getByRole('button',{name:/^Event(?:\s|$)/});
   if(!await eventChoice.count()){
     const allActions=dialog.getByRole('button',{name:'All actions',exact:true});
     if(await allActions.count())await allActions.click();
     eventChoice=dialog.getByRole('button',{name:/^Event(?:\s|$)/});
   }
   await expect(eventChoice.first()).toBeVisible();await eventChoice.first().click();
   dialog=page.getByRole('dialog');titleInput=dialog.getByLabel('Title',{exact:true});
 }
 const title=`Offline event ${Date.now()}`,editor=dialog;await expect(titleInput).toBeVisible();await titleInput.fill(title);await editor.getByRole('button',{name:'Add event',exact:true}).click();
 await expect(page.getByText(title,{exact:true})).toBeVisible();await page.reload();await expect(page.getByText(title,{exact:true})).toBeVisible();
 await page.getByText('Read-only external',{exact:true}).click();const detail=page.getByRole('dialog');await expect(detail.getByRole('button',{name:'Edit event',exact:true})).toHaveCount(0);await detail.locator('.sheet-close').click();
 await context.setOffline(false);await expect.poll(async()=>{const response=await page.request.get(`/api/events/?family=${family.id}&birthdays=0`);const value=await response.json();return (value.results||value).filter(event=>event.title===title).length},{timeout:20000}).toBe(1);
 await expect(page.locator('.offline-sync-pill')).toHaveText('Synced',{timeout:20000});
});
