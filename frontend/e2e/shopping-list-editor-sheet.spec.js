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
    await expect(dialog.getByRole('button',{name:'Liste löschen'})).toBeVisible();
    await expect(dialog.getByLabel('Name')).toBeFocused();
    const box=await dialog.boundingBox();
    expect(box.width).toBeLessThanOrEqual(width);
    await expectNoHorizontalOverflow(page);
    await dialog.getByRole('button',{name:'Abbrechen'}).click();
    await expect(dialog).toHaveCount(0);
  });
}

test('deleting a shopping list confirms the destructive action and falls back to the next list',async({page})=>{
  const state=await installApiMocks(page,{dismissOnboarding:true,language:'de'});
  state.shoppingLists.push({id:'shop-2',family:'family-1',name:'Drogerie',store:'Drogerie',icon:'cart-shopping',archived:false,sort_order:1,items:[{id:'item-2',shopping_list:'shop-2',name:'Seife',quantity:'1',category:'',aisle:'',note:'',favorite:false,checked:false,added_by_name:'Alex'}]});
  await page.route('**/api/shopping-lists/shop-1/',async route=>{
    if(route.request().method()!=='DELETE')return route.fallback();
    const index=state.shoppingLists.findIndex(row=>row.id==='shop-1');
    if(index>=0)state.shoppingLists.splice(index,1);
    await route.fulfill({status:204,body:''});
  });

  await page.goto('/?page=shopping');
  await page.waitForLoadState('networkidle');
  const overflow=page.locator('.shopping-overflow');
  await overflow.locator('summary').click();
  await page.getByRole('button',{name:'Liste bearbeiten'}).click();
  const editor=page.getByRole('dialog').filter({hasText:'Liste bearbeiten'});
  await editor.getByRole('button',{name:'Liste löschen'}).click();

  const confirm=page.getByRole('dialog').filter({hasText:'Einkaufsliste löschen?'});
  await expect(confirm).toContainText('Supermarkt');
  await expect(confirm).toContainText('alle enthaltenen Artikel');
  await confirm.getByRole('button',{name:'Liste löschen'}).click();

  await expect(editor).toHaveCount(0);
  await expect(page.locator('.shopping-session-title strong')).toHaveText('Drogerie');
  expect(state.shoppingLists.map(row=>row.name)).toEqual(['Drogerie']);
});

test('users without shopping-list management rights do not see permanent delete',async({page})=>{
  const state=await installApiMocks(page,{dismissOnboarding:true,language:'de'});
  state.shoppingLists[0].access={visibility:'family',visible_members:[],responsible_members:[],can_manage:false};
  await page.goto('/?page=shopping');
  await page.waitForLoadState('networkidle');
  await page.locator('.shopping-overflow summary').click();
  await page.getByRole('button',{name:'Liste bearbeiten'}).click();
  const editor=page.getByRole('dialog');
  await expect(editor.getByRole('button',{name:'Liste löschen'})).toHaveCount(0);
  await expect(editor.getByRole('button',{name:'Archivieren'})).toBeVisible();
});
