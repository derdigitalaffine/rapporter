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
 await expect(page.getByText('Family calendar',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Week',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByText('Familienkalender',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'List',exact:true}).click();
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

test('language control cycles through French Dutch and Thai and persists Thai',async({page})=>{
 await boot(page);
 await switchToEnglish(page);

 await page.getByRole('button',{name:/Language/i}).click();
 await expect(page.getByRole('heading',{name:'Plus',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:/Langue/i})).toBeVisible();

 await page.getByRole('button',{name:/Langue/i}).click();
 await expect(page.getByRole('heading',{name:'Meer',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:/Taal/i})).toBeVisible();

 await page.getByRole('button',{name:/Taal/i}).click();
 await expect(page.getByRole('heading',{name:'เพิ่มเติม',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:/ภาษา/})).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>localStorage.getItem('famuhle-language'))).toBe('th');

 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'ปฏิทิน',exact:true})).toBeVisible();
 await page.locator('.bottom-nav').getByRole('button',{name:'ปฏิทิน',exact:true}).click();
 await expect(page.getByText('ปฏิทินครอบครัว',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'สัปดาห์',exact:true})).toHaveAttribute('aria-pressed','true');
});
