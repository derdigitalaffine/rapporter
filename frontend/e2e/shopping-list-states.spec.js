import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,setup=()=>{},language='de'){
  const state=await installApiMocks(page,{dismissOnboarding:true,language});setup(state);await page.setViewportSize({width:390,height:844});await page.goto('/?page=shopping');await page.waitForLoadState('networkidle');await expect(page.locator('.shopping-page')).toBeVisible();return state;
}

test('shopping lists use one compact accessible switcher instead of a tab wall',async({page})=>{
  await boot(page,state=>{state.shoppingLists.push(
    {id:'shop-2',family:'family-1',name:'Drogerie',store:'dm',icon:'cart-shopping',archived:false,sort_order:1,items:[]},
    {id:'shop-3',family:'family-1',name:'Baumarkt',store:'',icon:'cart-shopping',archived:false,sort_order:2,items:[]},
  )});
  await expect(page.locator('.shopping-list-tabs')).toHaveCount(0);
  const select=page.getByLabel('Einkaufsliste wechseln');await expect(select).toBeVisible();await expect(select.locator('option')).toHaveCount(3);const box=await select.boundingBox();expect(box.height).toBeGreaterThanOrEqual(44);
  await select.selectOption('shop-2');await expect(page.locator('.shopping-session-title').getByText('Drogerie',{exact:true})).toBeVisible();await expect(page.getByText('Diese Liste ist noch leer',{exact:true})).toBeVisible();
});

test('shopping distinguishes no list and creates from the primary state CTA',async({page})=>{
  const state=await boot(page,state=>{state.shoppingLists=[]});await expect(page.getByText('Noch keine Einkaufsliste',{exact:true})).toBeVisible();await expect(page.locator('.smart-input')).toHaveCount(0);await page.getByRole('button',{name:'Einkaufsliste anlegen'}).click();const input=page.getByPlaceholder('Name der neuen Liste');await expect(input).toBeFocused();await input.fill('Wochenmarkt');await page.getByRole('button',{name:'Anlegen',exact:true}).click();await expect(page.locator('.shopping-session-title').getByText('Wochenmarkt',{exact:true})).toBeVisible();expect(state.shoppingLists.some(list=>list.name==='Wochenmarkt')).toBe(true);
});

test('empty list CTA focuses quick add while completed-only recovers through Store Erledigt',async({page})=>{
  const state=await boot(page,state=>{state.shoppingLists[0].items=[]});await expect(page.getByText('Diese Liste ist noch leer',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Ersten Artikel hinzufügen'}).click();await expect(page.locator('.smart-input input')).toBeFocused();
  state.shoppingLists[0].items=[{id:'done-1',shopping_list:'shop-1',name:'Schon gekauft',quantity:'1',category:'Vorrat',aisle:'',note:'',favorite:false,checked:true,position:1000,added_by_name:'Alex'}];await page.reload();await expect(page.getByText('Alles erledigt',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Erledigte ansehen'}).click();await expect(page.locator('.store-focus')).toBeVisible();await expect(page.getByRole('button',{name:/^Erledigt 1$/})).toHaveAttribute('aria-pressed','true');await expect(page.getByText('Schon gekauft',{exact:true})).toBeVisible();
});

test('offline is a persistent quiet state and English copy remains usable',async({page,context})=>{
  await boot(page,()=>{},'en');await context.setOffline(true);await expect(page.getByText('Offline – changes stay saved on this device.',{exact:true})).toBeVisible();await expect(page.getByLabel('Switch shopping list')).toHaveCount(0);await expect(page.getByRole('button',{name:'New list'})).toBeVisible();await context.setOffline(false);await expect(page.getByText('Offline – changes stay saved on this device.',{exact:true})).toHaveCount(0);
});
