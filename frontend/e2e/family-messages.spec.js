import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
import {installNativeChatMocks} from './native-chat-api.js';

test('family and system messages use canonical native chats with distinct write permissions',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await installApiMocks(page);const state=await installNativeChatMocks(page);
 await page.goto('/?page=inbox');await page.locator('.messenger-chat-row.family-chat').click();
 const input=page.getByRole('textbox',{name:'Nachricht',exact:true});
 await input.fill('Bitte Milch mitbringen');await input.press('Enter');
 await expect(page.locator('.messenger-bubble.own')).toContainText('Bitte Milch mitbringen');
 expect(state.rows['family-chat']).toHaveLength(1);expect(state.rows['family-chat'][0].client_id).toMatch(/^[0-9a-f-]{36}$/);
 await page.locator('.messenger-mobile-back').click();await page.locator('.messenger-chat-row.system-chat').click();
 await expect(page.locator('.messenger-bubble')).toContainText('Fenster schließen');await expect(input).toHaveCount(0);
 await expect(page.getByText('Dieser Chat ist nur lesbar.',{exact:true})).toBeVisible();await expect.poll(()=>state.system.unread).toBe(0);
 expect(state.requests.filter(row=>row.path.includes('system-chat/messages/')&&row.method==='POST')).toHaveLength(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.setViewportSize({width:1440,height:900});await page.reload();await page.locator('.messenger-chat-row.family-chat').click();
 await expect(page.locator('.messenger-bubble.own')).toContainText('Bitte Milch mitbringen');await expect(page.locator('#family-message-compose')).toHaveCount(0);
});
