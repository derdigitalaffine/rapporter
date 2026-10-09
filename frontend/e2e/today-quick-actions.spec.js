import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,viewport={width:390,height:844}){
  await page.setViewportSize(viewport);
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading',{name:/Hallo Familie|Hello family/})).toBeVisible();
}

function quickActions(page){return page.locator('.today-quick-actions')}

for(const viewport of [{width:390,height:844},{width:844,height:390}]){
  test(`Today task quick action opens editor in one tap and saves without navigation at ${viewport.width}x${viewport.height}`,async({page})=>{
    let created=null;await boot(page,viewport);
    await page.route('**/api/tasks/',async route=>{
      if(route.request().method()!=='POST')return route.fallback();
      created=route.request().postDataJSON();
      return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id:'today-task',...created,completed_at:null})});
    });
    await quickActions(page).getByRole('button',{name:/Hinzufügen · Aufgaben|Add · Tasks/}).click();
    await expect(page).toHaveURL(/127\.0\.0\.1:4173\/$/);
    const dialog=page.getByRole('dialog');
    await expect(dialog.getByRole('heading',{name:/Aufgabe hinzufügen|Add task/})).toBeVisible();
    const title=dialog.getByLabel(/Titel|Title/);await expect(title).toBeFocused();
    await title.fill('Direkt von Heute');
    await dialog.getByRole('button',{name:/Speichern|Save/,exact:true}).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(/127\.0\.0\.1:4173\/$/);
    await expect(page.getByRole('heading',{name:/Hallo Familie|Hello family/})).toBeVisible();
    expect(created?.title).toBe('Direkt von Heute');expect(created?.family).toBe('family-1');
  });
}

test('Today shopping quick action focuses the real item editor and Escape returns to Today without mutation',async({page})=>{
  let mutations=0;page.on('request',request=>{if(['POST','PATCH','DELETE'].includes(request.method())&&request.url().includes('/api/'))mutations++});
  await boot(page);
  await quickActions(page).getByRole('button',{name:/Hinzufügen · Einkauf|Add · Shopping/}).click();
  const dialog=page.getByRole('dialog');
  const item=dialog.getByRole('textbox',{name:/Artikel|Item/,exact:true});
  await expect(item).toBeVisible();await expect(item).toBeFocused();
  await expect(page).toHaveURL(/127\.0\.0\.1:4173\/$/);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);await expect(page).toHaveURL(/127\.0\.0\.1:4173\/$/);expect(mutations).toBe(0);
});

test('Today calendar quick action opens new event directly and Escape stays on Today',async({page})=>{
  await boot(page);
  await quickActions(page).getByRole('button',{name:/Hinzufügen · Kalender|Add · Calendar/}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByRole('heading',{name:/Termin hinzufügen|Add event/})).toBeVisible();
  await expect(dialog.getByLabel(/Titel|Title/)).toBeFocused();
  await expect(page).toHaveURL(/127\.0\.0\.1:4173\/$/);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);await expect(page).toHaveURL(/127\.0\.0\.1:4173\/$/);
});
