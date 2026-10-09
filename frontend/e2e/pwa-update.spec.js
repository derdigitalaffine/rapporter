import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page){
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading',{name:/Hallo Familie|Hello family/})).toBeVisible();
}

async function announceUpdate(page){
  await page.evaluate(()=>{
    window.__pwaActivationRequests=window.__pwaActivationRequests||0;
    window.dispatchEvent(new CustomEvent('famuhle:pwa-update-ready',{detail:{activate:()=>{window.__pwaActivationRequests+=1}}}));
  });
}

test('PWA update waits while a task editor has unsaved input and activates only on request',async({page})=>{
  await boot(page);
  await page.locator('.bottom-nav').getByRole('button',{name:'Aufgaben'}).click();
  await page.locator('.global-create-fab').click();
  const title=page.getByLabel('Titel');
  await expect(title).toBeFocused();
  await title.fill('Nicht verlieren');

  await announceUpdate(page);
  const banner=page.getByTestId('pwa-update-banner');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('Update bereit');
  await expect(banner).toContainText('ungespeicherten Eingaben');
  await expect(title).toHaveValue('Nicht verlieren');
  await expect(page.getByRole('dialog').getByRole('heading',{name:'Aufgabe hinzufügen'})).toBeVisible();
  expect(await page.evaluate(()=>window.__pwaActivationRequests)).toBe(0);

  await banner.getByRole('button',{name:'Später'}).click();
  await expect(banner).toHaveCount(0);
  await expect(title).toHaveValue('Nicht verlieren');

  await announceUpdate(page);
  await expect(banner).toBeVisible();
  await banner.getByRole('button',{name:'Jetzt aktualisieren'}).click();
  await expect.poll(()=>page.evaluate(()=>window.__pwaActivationRequests)).toBe(1);
});

test('service worker exposes controlled activation and still excludes private API responses',async({page})=>{
  await boot(page);
  const result=await page.evaluate(async()=>{
    if(!('serviceWorker' in navigator))return {supported:false};
    const registration=await navigator.serviceWorker.ready;
    const response=await fetch('/sw.js',{cache:'no-store'});
    const source=await response.text();
    const keys=await caches.keys();
    const urls=[];
    for(const key of keys){
      const cache=await caches.open(key);
      for(const request of await cache.keys())urls.push(new URL(request.url).pathname);
    }
    return {
      supported:true,
      active:Boolean(registration.active),
      controlledActivation:source.includes("event.data?.type==='SKIP_WAITING'")&&!source.includes('self.skipWaiting();\n  event.waitUntil(cacheAppShell())'),
      privateCached:urls.some(path=>path.startsWith('/api/')),
    };
  });
  expect(result.supported).toBe(true);
  expect(result.active).toBe(true);
  expect(result.controlledActivation).toBe(true);
  expect(result.privateCached).toBe(false);
});
