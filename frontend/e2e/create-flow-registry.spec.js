import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
import {installNativeChatMocks} from './native-chat-api.js';

async function boot(page){
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  const state=await installNativeChatMocks(page);
  await page.route('**/api/entitlements/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({tier:'family',display_name:'Family',capabilities:['vehicles','loyalty','pregnancy_baby','pets','travel']})}));
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  return state;
}

test('global create message action resolves through registry into inbox composer once',async({page})=>{
  await boot(page);
  await page.locator('.global-create-fab').click();
  const palette=page.getByRole('dialog',{name:'Neu hinzufügen'});
  await expect(palette).toBeVisible();
  await palette.getByRole('button',{name:'Alle Aktionen'}).click();
  const message=palette.getByRole('button',{name:'Mitteilung',exact:true});
  await expect(message).toBeVisible();
  await message.click();
  await expect(page).toHaveURL(/page=inbox/);
  await expect(page).not.toHaveURL(/compose=1/);
  const composer=page.locator('.messenger-composer');
  await expect(composer).toBeVisible();
  await expect(composer.getByRole('textbox',{name:'Nachricht',exact:true})).toBeFocused();
  await expect(page.locator('.messenger-chat-title')).toContainText('Familie');
  await page.locator('.messenger-mobile-back').click();
  await expect(composer).toHaveCount(0);
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#family-message-compose')).toHaveCount(0);
  await expect(page.locator('.messenger-composer')).toHaveCount(0);
});


test('compose shortcut never selects another family or a read-only system chat',async({page})=>{
 const state=await boot(page);state.family.family_id='family-2';
 await page.goto('/?page=inbox&compose=1');
 await expect(page.locator('.messenger-chat-list')).toBeVisible();
 await expect(page.locator('.messenger-composer')).toHaveCount(0);
 expect(state.requests.filter(row=>row.method==='POST'&&row.path.endsWith('/messages/'))).toHaveLength(0);
});
