import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function bootMore(page,{babyModule,petModule,language='de'}={}){
 await installApiMocks(page,{language,dismissOnboarding:true});
 if(babyModule)await page.route(/\/api\/baby\/module\/\?family=/,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(babyModule)}));
 if(petModule)await page.route(/\/api\/pets\/module\/\?family=/,route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(petModule)}));
 await page.goto('/?page=more');
 await page.waitForLoadState('networkidle');
 return page.locator('main[data-page="more"]');
}

test('More groups family features before organisation and administration without duplicating Calendar',async({page})=>{
 const main=await bootMore(page);
 await expect(main.getByRole('heading',{name:'Familie & Alltag',exact:true})).toBeVisible();
 await expect(main.getByRole('heading',{name:'Organisation',exact:true})).toBeVisible();
 await expect(main.getByRole('heading',{name:'Einstellungen & Verwaltung',exact:true})).toBeVisible();
 const sectionOrder=await main.locator('[data-more-section]').evaluateAll(nodes=>nodes.map(node=>node.dataset.moreSection));
 expect(sectionOrder).toEqual(['family','organisation','administration']);
 await expect(main.locator('[data-more-section="family"]')).toContainText('Pinnwand');
 await expect(main.locator('[data-more-section="family"]')).toContainText('Routinen');
 await expect(main.locator('[data-more-section="administration"]')).toContainText('Einstellungen');
 await expect(main.getByRole('button',{name:'Kalender',exact:true})).toHaveCount(0);
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Kalender',exact:true})).toBeVisible();
});

test('optional care modules are not duplicated when promoted to the main navigation',async({page})=>{
 const activeModule={enabled:true,authorized:true,can_manage:true,show_in_main_navigation:true};
 const main=await bootMore(page,{babyModule:activeModule,petModule:activeModule});
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Baby',exact:true})).toBeVisible();
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Tiere',exact:true})).toBeVisible();
 await expect(main.getByRole('button',{name:'Schwangerschaft & Baby',exact:true})).toHaveCount(0);
 await expect(main.getByRole('button',{name:'Haustiere',exact:true})).toHaveCount(0);
});

test('manageable care modules remain reachable from More while not in the main navigation',async({page})=>{
 const manageableModule={enabled:false,authorized:false,can_manage:true,show_in_main_navigation:false};
 const main=await bootMore(page,{babyModule:manageableModule,petModule:manageableModule});
 await expect(main.getByRole('button',{name:'Schwangerschaft & Baby',exact:true})).toBeVisible();
 await expect(main.getByRole('button',{name:'Haustiere',exact:true})).toBeVisible();
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Baby',exact:true})).toHaveCount(0);
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'Tiere',exact:true})).toHaveCount(0);
});
