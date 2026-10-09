import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,path='/'){
 await installApiMocks(page,{language:'de'});
 await page.goto(path);
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

 await page.goto('/?page=calendar');
 await page.waitForLoadState('networkidle');
 await expect(page.getByText('Family agenda',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:/Show past/})).toBeVisible();
 await expect(page.getByText('Vergangene anzeigen',{exact:true})).toHaveCount(0);
 const dayHeading=page.locator('.agenda-day-head small').first();
 await expect(dayHeading).not.toContainText(/HEUTE|MORGEN|GESTERN/);

 await page.goto('/?page=integrations');
 await page.waitForLoadState('networkidle');
 await expect(page.getByText('Connection needs attention',{exact:true})).toBeVisible();
 await expect(page.getByText(/Next automatic retry/)).toBeVisible();
 await expect(page.getByText(/Nächster automatischer Versuch/)).toHaveCount(0);
 await expect(page.locator('.integration-recovery small')).toContainText(/in .*hour/);
});
