import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,viewport={width:390,height:844}){
  await page.setViewportSize(viewport);
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading',{name:/Hallo Familie|Hello family/})).toBeVisible();
}

async function fab(page){const button=page.locator('.global-create-fab');await expect(button).toBeVisible();return button}

async function boxesDoNotOverlap(a,b){const x=await a.boundingBox(),y=await b.boundingBox();expect(x).not.toBeNull();expect(y).not.toBeNull();const overlap=!(x.x+x.width<=y.x||y.x+y.width<=x.x||x.y+x.height<=y.y||y.y+y.height<=x.y);expect(overlap).toBe(false)}

test('Heute -> global create palette -> Aufgabe -> save returns to Heute',async({page})=>{
  let created=null;
  await page.route('**/api/tasks/',async route=>{
    if(route.request().method()!=='POST')return route.fallback();
    created=route.request().postDataJSON();
    return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id:'task-created',...created,completed_at:null})});
  });
  await boot(page);
  const button=await fab(page);
  await expect(button).toHaveAttribute('aria-label','Hinzufügen');
  await button.click();
  const palette=page.getByRole('dialog',{name:'Neu hinzufügen'});
  await expect(palette).toBeVisible();
  await palette.getByRole('button',{name:'Aufgabe'}).click();
  const title=page.getByLabel('Titel');
  await expect(title).toBeFocused();
  await title.fill('Schuhe für morgen bereitstellen');
  await page.getByRole('button',{name:'Speichern'}).click();
  await expect(page.getByRole('heading',{name:/Hallo Familie/})).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(created?.family).toBe('family-1');
  expect(created?.title).toBe('Schuhe für morgen bereitstellen');
});

test('Aufgaben opens the shared Task editor with one FAB tap',async({page})=>{
  await boot(page);
  await page.locator('.bottom-nav').getByRole('button',{name:'Aufgaben'}).click();
  const button=await fab(page);
  await expect(button).toHaveAttribute('aria-label','Aufgabe hinzufügen');
  await button.click();
  await expect(page.getByRole('dialog').getByRole('heading',{name:'Aufgabe hinzufügen'})).toBeVisible();
  await expect(page.getByLabel('Titel')).toBeFocused();
});

test('Einkauf opens item entry for the active shopping list with one FAB tap',async({page})=>{
  await boot(page);
  await page.locator('.bottom-nav').getByRole('button',{name:'Einkauf'}).click();
  const button=await fab(page);
  await expect(button).toHaveAttribute('aria-label','Einkaufsartikel hinzufügen');
  await button.click();
  const item=page.getByLabel('Artikel');
  await expect(item).toBeVisible();
  await expect(item).toBeFocused();
});

test('Kalender opens a new event directly with one FAB tap',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto('/calendar');
  await page.waitForLoadState('networkidle');
  const button=await fab(page);
  await expect(button).toHaveAttribute('aria-label','Termin hinzufügen');
  await button.click();
  await expect(page.getByRole('dialog').getByRole('heading',{name:'Termin hinzufügen'})).toBeVisible();
  await expect(page.getByLabel('Titel')).toBeFocused();
});

test('palette closes with Escape without creating data and restores FAB focus',async({page})=>{
  let mutations=0;
  page.on('request',request=>{if(['POST','PATCH','DELETE'].includes(request.method())&&request.url().includes('/api/'))mutations++});
  await boot(page);
  const button=await fab(page);
  await button.click();
  await expect(page.getByRole('dialog',{name:'Neu hinzufügen'})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog',{name:'Neu hinzufügen'})).toHaveCount(0);
  await expect(button).toBeFocused();
  expect(mutations).toBe(0);
});

test('guest gets content create actions but no forbidden administration or unavailable message action',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  const guestFamily={id:'family-1',name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-1',family:'family-1',user:1,username:'alex',role:'guest',display_name:'Alex',avatar:''}]};
  await page.route('**/api/families/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([guestFamily])}));
  await page.goto('/');await page.waitForLoadState('networkidle');
  await (await fab(page)).click();
  const palette=page.getByRole('dialog',{name:'Neu hinzufügen'});
  await expect(palette.getByRole('button',{name:'Aufgabe'})).toBeVisible();
  await expect(palette.getByRole('button',{name:'Einkaufsartikel'})).toBeVisible();
  await expect(palette.getByRole('button',{name:'Termin'})).toBeVisible();
  await expect(palette.getByRole('button',{name:'Mitteilung'})).toHaveCount(0);
  await expect(palette.getByText('Integrationen')).toHaveCount(0);
  await expect(palette.getByText('Automationen')).toHaveCount(0);
});

for(const viewport of [{width:390,height:844},{width:844,height:390}]){
  test(`FAB stays clear of bottom navigation at ${viewport.width}x${viewport.height}`,async({page})=>{
    await boot(page,viewport);
    const button=await fab(page),nav=page.locator('.bottom-nav');
    await expect(nav).toBeVisible();
    await boxesDoNotOverlap(button,nav);
    const box=await button.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(viewport.width+1);expect(box.y).toBeGreaterThanOrEqual(0);
  });
}

test('desktop FAB is separated from sidebar navigation and inside the viewport',async({page})=>{
  const viewport={width:1440,height:900};await boot(page,viewport);
  const button=await fab(page),nav=page.locator('.bottom-nav');await boxesDoNotOverlap(button,nav);
  const box=await button.boundingBox();expect(box.x).toBeGreaterThan(900);expect(box.x+box.width).toBeLessThanOrEqual(viewport.width);expect(box.y+box.height).toBeLessThanOrEqual(viewport.height);
});
