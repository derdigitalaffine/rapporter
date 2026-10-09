import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page){
 await installApiMocks(page,{language:'de'});
 await page.goto('/?page=shopping');
 await page.waitForLoadState('networkidle');
 await expect(page.getByText('Milch',{exact:true})).toBeVisible();
}

test('shopping check and add survive offline reload and sync on reconnect',async({page,context})=>{
 await boot(page);
 await context.setOffline(true);

 await page.getByRole('button',{name:/Milch · Erledigen/}).click();
 await page.getByPlaceholder('Artikel suchen oder hinzufügen …').fill('Brot');
 await page.getByRole('button',{name:/Hinzufügen/}).click();
 await expect(page.getByText('Brot',{exact:true})).toBeVisible();
 await expect(page.getByText(/Noch nicht synchronisiert/).first()).toBeVisible();

 await page.reload({waitUntil:'domcontentloaded'});
 await expect(page.getByText('Brot',{exact:true})).toBeVisible();
 await expect(page.getByText(/Noch nicht synchronisiert/).first()).toBeVisible();

 await context.setOffline(false);
 await expect(page.getByText('Brot',{exact:true})).toBeVisible();
 await expect(page.locator('.metric-row .warn')).toHaveCount(0,{timeout:10000});

 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect(page.getByText('Brot',{exact:true})).toBeVisible();
 await expect(page.locator('.done-items')).toContainText('Milch');
});
