import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page){
 await installApiMocks(page,{language:'de'});
 await page.goto('/');
 await page.waitForLoadState('networkidle');
}

async function switchToEnglish(page){
 await page.locator('.bottom-nav').getByRole('button',{name:/^Mehr$/}).click();
 await page.getByRole('button',{name:/Sprache/i}).click();
 await expect(page.getByRole('heading',{name:'More',exact:true})).toBeVisible();
}

test('DE to EN also changes calendar and integration locale-sensitive copy',async({page})=>{
 await boot(page);
 await switchToEnglish(page);

 await page.locator('.bottom-nav').getByRole('button',{name:'Calendar',exact:true}).click();
 await expect(page.getByText('Family agenda',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:/Show past/})).toBeVisible();
 await expect(page.getByText('Vergangene anzeigen',{exact:true})).toHaveCount(0);
 const dayHeading=page.locator('.agenda-day-head small').first();
 await expect(dayHeading).not.toContainText(/HEUTE|MORGEN|GESTERN/);

 await page.getByRole('button',{name:'Back',exact:true}).click();
 await page.getByRole('button',{name:'Integrations',exact:true}).click();
 await expect(page.getByText('Connection needs attention',{exact:true})).toBeVisible();
 await expect(page.getByText(/Next automatic retry/)).toBeVisible();
 await expect(page.getByText(/Nächster automatischer Versuch/)).toHaveCount(0);
 await expect(page.locator('.integration-recovery small')).toContainText(/in \d+ (?:minute|minutes|hour|hours)/);
});
