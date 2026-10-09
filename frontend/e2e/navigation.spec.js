import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,path='/'){
 await installApiMocks(page,{language:'de'});
 await page.goto(path);
 await page.waitForLoadState('networkidle');
}

test('main areas keep stable URLs across reload',async({page})=>{
 await boot(page,'/?page=tasks');
 await expect(page.getByRole('heading',{name:'Aufgaben',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=tasks$/);

 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect(page.getByRole('heading',{name:'Aufgaben',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=tasks$/);

 await page.locator('.bottom-nav').getByRole('button',{name:'Einkauf',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Einkauf',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=shopping$/);
});

test('browser back and forward follow previous app areas',async({page})=>{
 await boot(page);
 await page.locator('.bottom-nav').getByRole('button',{name:'Aufgaben',exact:true}).click();
 await page.locator('.bottom-nav').getByRole('button',{name:'Einkauf',exact:true}).click();
 await expect(page).toHaveURL(/\?page=shopping$/);

 await page.goBack();
 await expect(page.getByRole('heading',{name:'Aufgaben',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=tasks$/);

 await page.goForward();
 await expect(page.getByRole('heading',{name:'Einkauf',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=shopping$/);
});

test('detail back returns to previous app area and direct links have a fallback',async({page})=>{
 await boot(page);
 await page.locator('.bottom-nav').getByRole('button',{name:'Mehr',exact:true}).click();
 await page.getByRole('button',{name:'Kalender',exact:true}).click();
 await expect(page).toHaveURL(/\?page=calendar$/);
 await page.getByRole('button',{name:'Zurück',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Mehr',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=more$/);

 await page.goto('/?page=integrations');
 await page.waitForLoadState('networkidle');
 await expect(page.getByRole('heading',{name:'Integrationen',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Zurück',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Mehr',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=more$/);
});

test('integration callback is normalized to the integrations deep link',async({page})=>{
 await boot(page,'/?integration_connected=Testkalender');
 await expect(page.getByRole('heading',{name:'Integrationen',exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=integrations$/);
});
