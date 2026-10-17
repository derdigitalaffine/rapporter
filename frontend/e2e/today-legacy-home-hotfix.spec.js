import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('canonical home never loads legacy layout and legacy start is surfaced only under More',async({page})=>{
 await installApiMocks(page,{language:'de',dismissOnboarding:true});
 const legacyLayoutRequests=[];
 page.on('request',request=>{
  if(new URL(request.url()).pathname==='/api/today-layout/')legacyLayoutRequests.push(request.method());
 });

 await page.goto('/');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('[data-testid="today-canonical-home"]')).toBeVisible();
 await expect(page.locator('[data-testid="legacy-today-home"]')).toHaveCount(0);
 await expect(page.locator('[data-testid="today-canonical-grid"] [data-today-widget]')).toHaveCount(3);
 expect(legacyLayoutRequests).toEqual([]);
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Alter Legacy-Startscreen',exact:true})).toHaveCount(0);

 await page.locator('.bottom-nav').getByRole('button',{name:'Mehr',exact:true}).click();
 const more=page.locator('main[data-page="more"]');
 const legacyEntry=more.getByRole('button',{name:'Alter Legacy-Startscreen',exact:true});
 await expect(legacyEntry).toBeVisible();
 await legacyEntry.click();
 await expect(page).toHaveURL(/\?page=legacy-home$/);
 await expect(page.locator('[data-testid="legacy-today-home"]')).toBeVisible();
 await expect(page.getByRole('heading',{name:'Alter Legacy-Startscreen',exact:true})).toBeVisible();
 await expect.poll(()=>legacyLayoutRequests.filter(method=>method==='GET').length).toBeGreaterThan(0);
 await expect(page.locator('.bottom-nav')).toHaveCount(0);
});
