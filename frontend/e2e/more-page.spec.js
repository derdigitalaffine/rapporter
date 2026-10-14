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

test('More sections collapse and keep their state after reload',async({page})=>{
 const main=await bootMore(page);
 const familySection=main.locator('[data-more-section="family"]');
 const toggle=familySection.locator('[data-more-toggle="family"]');
 await expect(toggle).toHaveAttribute('aria-expanded','true');
 await toggle.click();
 await expect(toggle).toHaveAttribute('aria-expanded','false');
 await expect(familySection.getByRole('button',{name:'Pinnwand',exact:true})).toBeHidden();
 await page.reload();
 await page.waitForLoadState('networkidle');
 const reloaded=page.locator('main[data-page="more"] [data-more-section="family"]');
 await expect(reloaded.locator('[data-more-toggle="family"]')).toHaveAttribute('aria-expanded','false');
 await expect(reloaded.getByRole('button',{name:'Pinnwand',exact:true})).toBeHidden();
});

test('More sections can be reordered by drag and drop and persist',async({page})=>{
 const main=await bootMore(page);
 const administrationHandle=main.locator('[data-more-drag-handle="administration"]');
 const familySection=main.locator('[data-more-section="family"]');
 await administrationHandle.dragTo(familySection);
 await expect.poll(()=>main.locator('[data-more-section]').evaluateAll(nodes=>nodes.map(node=>node.dataset.moreSection))).toEqual(['administration','family','organisation']);
 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect.poll(()=>page.locator('main[data-page="more"] [data-more-section]').evaluateAll(nodes=>nodes.map(node=>node.dataset.moreSection))).toEqual(['administration','family','organisation']);
});

test('More section order is keyboard-reorderable from the drag handle',async({page})=>{
 const main=await bootMore(page);
 const organisationHandle=main.locator('[data-more-drag-handle="organisation"]');
 await organisationHandle.focus();
 await page.keyboard.press('ArrowUp');
 await expect.poll(()=>main.locator('[data-more-section]').evaluateAll(nodes=>nodes.map(node=>node.dataset.moreSection))).toEqual(['organisation','family','administration']);
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