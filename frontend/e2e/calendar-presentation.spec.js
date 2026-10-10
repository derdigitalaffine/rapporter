import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function bootCalendar(page,{mobile=false}={}){
 if(mobile)await page.setViewportSize({width:390,height:844});
 await installApiMocks(page);
 await page.goto('/?page=calendar');
}

test('calendar defaults to week and switches week month list without horizontal overflow',async({page})=>{
 await bootCalendar(page,{mobile:true});
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.calendar-week-view')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Monat',exact:true}).click();
 await expect(page.getByRole('button',{name:'Monat',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.calendar-month-view')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Liste',exact:true}).click();
 await expect(page.getByRole('button',{name:'Liste',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page).toHaveURL(/view=list/);
 await expect(page.getByText('Kinderarzt',{exact:true})).toBeVisible();
});

test('calendar view survives a reload through URL state',async({page})=>{
 await bootCalendar(page);
 await page.getByRole('button',{name:'Monat',exact:true}).click();
 await expect(page).toHaveURL(/view=month/);
 await page.reload();
 await expect(page.getByRole('button',{name:'Monat',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.calendar-month-view')).toBeVisible();
});

test('Today week compass navigates weeks, resets to today and opens tapped day in calendar',async({page})=>{
 await installApiMocks(page);
 await page.goto('/');
 const compass=page.getByTestId('week-compass');
 await expect(compass).toBeVisible();
 const heading=compass.getByRole('heading');
 const initial=await heading.textContent();
 await compass.getByRole('button',{name:'Nächste Woche'}).click();
 await expect(heading).not.toHaveText(initial||'');
 await expect(compass.getByRole('button',{name:'Heute',exact:true})).toBeVisible();
 await compass.getByRole('button',{name:'Heute',exact:true}).click();
 await expect(heading).toHaveText(initial||'');
 await compass.locator('.week-compass-days button').first().click();
 await expect(page).toHaveURL(/page=calendar&day=\d{4}-\d{2}-\d{2}/);
 await expect(page.getByRole('button',{name:'Woche',exact:true})).toHaveAttribute('aria-pressed','true');
});
