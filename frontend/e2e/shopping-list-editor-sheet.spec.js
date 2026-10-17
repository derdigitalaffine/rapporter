import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function expectNoHorizontalOverflow(page){
  const sizes=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth}));
  expect(sizes.scrollWidth).toBeLessThanOrEqual(sizes.clientWidth);
}

async function openListEditor(page,width){
  await installApiMocks(page,{dismissOnboarding:true,language:'de'});
  await page.setViewportSize({width,height:844});
  await page.goto('/?page=shopping');
  await page.waitForLoadState('networkidle');
  const overflow=page.locator('.shopping-overflow');
  await overflow.locator('summary').click();
  await page.getByRole('button',{name:'Liste bearbeiten'}).click();
  return page.getByRole('dialog');
}

for(const width of [320,390]){
  test(`list editor uses the global sheet and form contract at ${width}px`,async({page})=>{
    const dialog=await openListEditor(page,width);
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveClass(/quick-sheet/);
    await expect(dialog.locator('form.form-shell')).toBeVisible();
    await expect(dialog.locator('form.quick-form')).toHaveCount(0);
    await expect(dialog.locator('.form-actions')).toBeVisible();
    await expect(dialog.getByRole('button',{name:'Abbrechen'})).toBeVisible();
    await expect(dialog.getByRole('button',{name:'Speichern'})).toBeVisible();
    await expect(dialog.getByLabel('Name')).toBeFocused();
    const box=await dialog.boundingBox();
    expect(box.width).toBeLessThanOrEqual(width);
    await expectNoHorizontalOverflow(page);
    await dialog.getByRole('button',{name:'Abbrechen'}).click();
    await expect(dialog).toHaveCount(0);
  });
}

test('manager can permanently delete a shopping list with explicit confirmation',async({page})=>{
  await installApiMocks(page,{dismissOnboarding:true,language:'de'});
  let deleted=false;
  const list={id:'shop-1',family:'family-1',name:'Supermarkt',store:'Markt',icon:'cart-shopping',archived:false,sort_order:0,items:[{id:'item-1',shopping_list:'shop-1',name:'Milch',quantity:'1 l',checked:false}],open_count:1,checked_count:0,access:{visibility:'family',visible_members:[],responsible_members:[],can_manage:true}};
  await page.route('**/api/shopping-lists/',async route=>{
    if(route.request().method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(deleted?[]:[list])});
    return route.fallback();
  });
  await page.route('**/api/shopping-lists/shop-1/',async route=>{
    if(route.request().method()==='DELETE'){deleted=true;return route.fulfill({status:204,body:''});}
    return route.fallback();
  });
  await page.setViewportSize({width:390,height:844});
  await page.goto('/?page=shopping');
  await page.waitForLoadState('networkidle');
  await page.locator('.shopping-overflow summary').click();
  await page.getByRole('button',{name:'Liste bearbeiten'}).click();
  const editor=page.getByRole('dialog');
  await expect(editor.getByRole('button',{name:'Dauerhaft löschen'})).toBeVisible();
  await editor.getByRole('button',{name:'Dauerhaft löschen'}).click();
  const confirm=page.getByRole('dialog').last();
  await expect(confirm).toContainText('Supermarkt');
  await expect(confirm).toContainText('Alle enthaltenen Artikel werden ebenfalls gelöscht');
  await confirm.getByRole('button',{name:'Dauerhaft löschen'}).click();
  await expect.poll(()=>deleted).toBe(true);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('[data-state="no-list"]')).toBeVisible();
});

test('permanent delete is hidden without shopping manage permission',async({page})=>{
  await installApiMocks(page,{dismissOnboarding:true,language:'de'});
  const list={id:'shop-1',family:'family-1',name:'Supermarkt',store:'Markt',icon:'cart-shopping',archived:false,sort_order:0,items:[],open_count:0,checked_count:0,access:{visibility:'family',visible_members:[],responsible_members:[],can_manage:false}};
  await page.route('**/api/shopping-lists/',async route=>route.request().method()==='GET'?route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([list])}):route.fallback());
  await page.setViewportSize({width:390,height:844});
  await page.goto('/?page=shopping');
  await page.waitForLoadState('networkidle');
  await page.locator('.shopping-overflow summary').click();
  await page.getByRole('button',{name:'Liste bearbeiten'}).click();
  await expect(page.getByRole('dialog').getByRole('button',{name:'Dauerhaft löschen'})).toHaveCount(0);
});
