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
