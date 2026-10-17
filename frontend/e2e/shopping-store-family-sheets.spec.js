import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const sessionId='11111111-1111-4111-8111-111111111111';
const activeSession=()=>({
 id:sessionId,
 shopping_list:'shop-1',
 status:'active',
 started_at:new Date().toISOString(),
 completed_at:null,
 last_activity_at:new Date().toISOString(),
 started_by:{id:1,name:'Alex',avatar:'',is_self:true},
 completed_by:null,
 participants:[{id:1,name:'Alex',avatar:'',is_self:true}],
});

async function bootStore(page,{session=false}={}){
 await installApiMocks(page,{dismissOnboarding:true,language:'de'});
 if(session){
  await page.route('**/api/shopping-sessions/start/',route=>route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[],created:true})}));
  await page.route('**/api/shopping-sessions/current/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session:activeSession(),cursor:0,activities:[]})}));
 }
 await page.setViewportSize({width:390,height:844});
 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.store-focus')).toBeVisible();
}

test('store add uses the canonical FamilySheet contract',async({page})=>{
 await bootStore(page);
 const trigger=page.locator('.store-footer').getByRole('button',{name:'Artikel hinzufügen'});
 await trigger.click();
 const dialog=page.getByRole('dialog');
 await expect(dialog).toHaveClass(/family-sheet/);
 await expect(dialog).toHaveAttribute('data-family-overlay-owner','base-ui');
 await expect(dialog.locator('input')).toBeFocused();
 await page.keyboard.press('Escape');
 await expect(dialog).toHaveCount(0);
 await expect(trigger).toBeFocused();
});

test('store checkout review uses the canonical FamilySheet contract',async({page})=>{
 await bootStore(page,{session:true});
 await page.locator('.store-check').first().click();
 await page.getByRole('button',{name:'Einkauf abschließen'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByRole('heading',{name:'Einkauf abschließen'})).toBeVisible();
 await expect(dialog).toHaveClass(/family-sheet/);
 await expect(dialog).toHaveAttribute('data-family-overlay-owner','base-ui');
 await page.keyboard.press('Escape');
 await expect(dialog).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Einkauf abschließen'})).toBeFocused();
});
