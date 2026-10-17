import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const actionPayload={actions:[{
 id:'action-priority-1',family:'family-1',kind:'task',title:'Versicherung heute klären',state:'due',priority:'high',urgency:'high',ranking:{bucket:1},deep_link:'/?page=todo',due_at:new Date(Date.now()+3600000).toISOString(),
}]};

test('canonical home uses the confirmed core default and remains independently personalizable',async({page})=>{
 await installApiMocks(page,{language:'de',dismissOnboarding:true});
 const legacyLayoutRequests=[];
 page.on('request',request=>{if(new URL(request.url()).pathname==='/api/today-layout/')legacyLayoutRequests.push(request.method())});

 await page.goto('/');
 await page.waitForLoadState('networkidle');
 const grid=page.locator('[data-testid="today-canonical-grid"]');
 await expect(grid.locator('[data-today-widget]')).toHaveCount(7);
 await expect(grid.locator('[data-today-widget="situation"]')).toBeVisible();
 await expect(grid.locator('[data-today-widget="focus"]')).toBeVisible();
 await expect(grid.locator('[data-today-widget="timeline"]')).toBeVisible();
 await expect(grid.locator('[data-today-widget="week"]')).toBeVisible();
 await expect(grid.locator('[data-today-widget="todo"]')).toBeVisible();
 await expect(grid.locator('[data-today-widget="quick-actions"]')).toBeVisible();
 await expect(grid.locator('[data-today-widget="pinboard"]')).toBeVisible();
 await expect(grid.locator('[data-today-widget="overview"]')).toHaveCount(0);
 await expect(page.locator('[data-testid="today-quick-actions"] .create-action-card').first()).toBeVisible();
 await expect(page.locator('[data-testid="today-layout-edit"]')).toBeVisible();
 expect(legacyLayoutRequests).toEqual([]);

 await page.locator('[data-testid="today-layout-edit"]').click();
 const shoppingCard=page.locator('[data-library-widget="shopping"]');
 await expect(shoppingCard).toBeVisible();
 await shoppingCard.getByRole('button',{name:'Hinzufügen'}).click();
 const shoppingRow=page.locator('[data-editor-widget-id="shopping"]');
 await expect(shoppingRow).toBeVisible();
 await shoppingRow.getByRole('combobox',{name:/Einkauf · Größe/}).selectOption('wide-compact');

 const shoppingDrag=page.locator('[data-testid="today-drag-shopping"]');
 await shoppingDrag.focus();
 await page.keyboard.press('Space');
 await page.keyboard.press('ArrowUp');
 await page.keyboard.press('Enter');
 await page.locator('[data-editor-widget-id="focus"]').getByRole('button',{name:'Ausblenden'}).click();
 await page.getByRole('button',{name:'Speichern'}).click();

 await expect(grid.locator('[data-today-widget="shopping"]')).toHaveAttribute('data-widget-size','wide-compact');
 await expect(grid.locator('[data-today-widget="focus"]')).toHaveCount(0);
 expect(legacyLayoutRequests).toEqual([]);

 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect(page.locator('[data-testid="today-canonical-grid"] [data-today-widget="shopping"]')).toHaveAttribute('data-widget-size','wide-compact');
 await expect(page.locator('[data-testid="today-canonical-grid"] [data-today-widget="focus"]')).toHaveCount(0);
 expect(legacyLayoutRequests).toEqual([]);
});

test('priority banner is red-alert content and configurable from the home editor',async({page})=>{
 await installApiMocks(page,{language:'de',dismissOnboarding:true});
 await page.route('**/api/actions/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(actionPayload)}));

 await page.goto('/');
 await page.waitForLoadState('networkidle');
 const banner=page.locator('[data-testid="today-priority-banner"]');
 await expect(banner).toBeVisible();
 await expect(banner).toContainText('Versicherung heute klären');

 await page.locator('[data-testid="today-layout-edit"]').click();
 const settings=page.locator('[data-testid="today-priority-settings"]');
 await expect(settings).toBeVisible();
 await settings.getByRole('checkbox',{name:'Prioritätsbanner anzeigen'}).uncheck();
 await expect(banner).toHaveCount(0);
 await page.getByRole('button',{name:'Abbrechen'}).click();

 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect(page.locator('[data-testid="today-priority-banner"]')).toHaveCount(0);
});

test('shopping tile can exclude individual shopping lists from its sum and persists the choice',async({page})=>{
 const state=await installApiMocks(page,{language:'de',dismissOnboarding:true});
 state.shoppingLists.push({
  id:'shop-2',family:'family-1',name:'Drogerie',store:'Drogerie',icon:'cart-shopping',archived:false,sort_order:1,
  items:[
   {id:'item-2',shopping_list:'shop-2',name:'Zahnpasta',checked:false},
   {id:'item-3',shopping_list:'shop-2',name:'Seife',checked:false},
  ],
 });

 await page.goto('/');
 await page.waitForLoadState('networkidle');
 await page.locator('[data-testid="today-layout-edit"]').click();
 await page.locator('[data-library-widget="shopping"]').getByRole('button',{name:'Hinzufügen'}).click();

 const tileValue=page.locator('[data-testid="today-canonical-grid"] [data-today-widget="shopping"] .today-module-shortcut-value');
 await expect(tileValue).toHaveText('3');
 const settings=page.locator('[data-testid="today-shopping-list-settings"]');
 await expect(settings.getByRole('checkbox',{name:'Supermarkt · 1 offen'})).toBeChecked();
 await expect(settings.getByRole('checkbox',{name:'Drogerie · 2 offen'})).toBeChecked();
 await settings.getByRole('checkbox',{name:'Drogerie · 2 offen'}).uncheck();
 await expect(tileValue).toHaveText('1');
 await page.getByRole('button',{name:'Speichern'}).click();

 await page.reload();
 await page.waitForLoadState('networkidle');
 await expect(page.locator('[data-testid="today-canonical-grid"] [data-today-widget="shopping"] .today-module-shortcut-value')).toHaveText('1');
 await page.locator('[data-testid="today-layout-edit"]').click();
 await expect(page.locator('[data-testid="today-shopping-list-settings"]').getByRole('checkbox',{name:'Drogerie · 2 offen'})).not.toBeChecked();
});
