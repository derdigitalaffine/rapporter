import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,setup=()=>{},language='de',viewport={width:390,height:844}){
  const state=await installApiMocks(page,{dismissOnboarding:true,language});setup(state);await page.setViewportSize(viewport);await page.goto('/?page=shopping');await page.waitForLoadState('networkidle');await expect(page.locator('.shopping-page')).toBeVisible();return state;
}

async function expectNoHorizontalOverflow(page){
  const sizes=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth}));expect(sizes.scrollWidth).toBeLessThanOrEqual(sizes.clientWidth);
}

test('shopping list switcher scales from quick choices to a compact select',async({page})=>{
  const state=await boot(page,state=>{state.shoppingLists.push(
    {id:'shop-2',family:'family-1',name:'Drogerie',store:'dm',icon:'cart-shopping',archived:false,sort_order:1,items:[]},
    {id:'shop-3',family:'family-1',name:'Baumarkt und Garten',store:'',icon:'cart-shopping',archived:false,sort_order:2,items:[]},
  )},'de',{width:320,height:844});
  await expect(page.locator('.shopping-list-tabs')).toHaveCount(0);
  const quick=page.locator('.shopping-list-switcher-quick');await expect(quick).toBeVisible();await expect(quick.getByRole('button')).toHaveCount(3);await expect(page.locator('.shopping-list-switcher-select')).toHaveCount(0);
  const quickBox=await quick.getByRole('button').first().boundingBox();expect(quickBox.height).toBeGreaterThanOrEqual(48);
  const createButton=page.getByRole('button',{name:'Neue Liste'});const createBox=await createButton.boundingBox();expect(createBox.width).toBeGreaterThanOrEqual(48);expect(createBox.height).toBeGreaterThanOrEqual(48);await expectNoHorizontalOverflow(page);
  await quick.getByRole('button',{name:/^Drogerie/}).click();await expect(page.locator('.shopping-session-title').getByText('Drogerie',{exact:true})).toBeVisible();await expect(page.getByText('Diese Liste ist noch leer',{exact:true})).toBeVisible();
  state.shoppingLists.push(
    {id:'shop-4',family:'family-1',name:'Getränke',store:'',icon:'cart-shopping',archived:false,sort_order:3,items:[]},
    {id:'shop-5',family:'family-1',name:'Apotheke',store:'',icon:'cart-shopping',archived:false,sort_order:4,items:[]},
  );
  await page.reload();await expect(page.locator('.shopping-list-switcher-quick')).toHaveCount(0);const select=page.getByLabel('Einkaufsliste wechseln');await expect(select).toBeVisible();await expect(select.locator('option')).toHaveCount(5);const selectBox=await select.boundingBox();expect(selectBox.height).toBeGreaterThanOrEqual(48);expect(parseFloat(await select.evaluate(element=>getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(16);await expectNoHorizontalOverflow(page);
  await page.setViewportSize({width:1024,height:768});await expect(createButton.locator('span')).toBeVisible();await expectNoHorizontalOverflow(page);
});

test('planning keeps add and store primary while management stays in More',async({page})=>{
  await boot(page,()=>{},'de',{width:320,height:844});
  await expect(page.locator('.smart-input input')).toBeVisible();
  await expect(page.locator('.shopping-mode-toggle')).toHaveCount(0);
  const store=page.locator('.shopping-store-entry');await expect(store).toBeVisible();const storeBox=await store.boundingBox();expect(storeBox.height).toBeGreaterThanOrEqual(48);
  const overflow=page.locator('.shopping-overflow');const summary=overflow.locator('summary');await expect(summary).toBeVisible();const summaryBox=await summary.boundingBox();expect(summaryBox.width).toBeGreaterThanOrEqual(48);expect(summaryBox.height).toBeGreaterThanOrEqual(48);
  await expect(overflow.locator('.shopping-overflow-menu')).toBeHidden();await expect(page.getByRole('button',{name:'Liste bearbeiten'})).toBeHidden();await expect(page.getByRole('button',{name:'Textmodus'})).toBeHidden();
  await summary.click();await expect(page.getByRole('button',{name:'Liste bearbeiten'})).toBeVisible();await expect(page.getByRole('button',{name:'Textmodus'})).toBeVisible();await expectNoHorizontalOverflow(page);
  await page.getByRole('button',{name:'Liste bearbeiten'}).click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Bearbeiten'})).toBeVisible();
});

test('shopping distinguishes no list and creates from the primary state CTA',async({page})=>{
  const state=await boot(page,state=>{state.shoppingLists=[]});await expect(page.getByText('Noch keine Einkaufsliste',{exact:true})).toBeVisible();await expect(page.locator('.smart-input')).toHaveCount(0);const createButton=page.getByRole('button',{name:'Einkaufsliste anlegen'});const box=await createButton.boundingBox();expect(box.height).toBeGreaterThanOrEqual(48);await createButton.click();const input=page.getByPlaceholder('Name der neuen Liste');await expect(input).toBeFocused();await expect(page.getByText('Für wen?',{exact:true})).toBeVisible();await expect(page.getByRole('radio',{name:'Ganze Familie'})).toHaveAttribute('aria-checked','true');await input.fill('Wochenmarkt');await page.getByRole('button',{name:'Anlegen',exact:true}).click();await expect(page.locator('.shopping-session-title').getByText('Wochenmarkt',{exact:true})).toBeVisible();expect(state.shoppingLists.some(list=>list.name==='Wochenmarkt')).toBe(true);
});

test('empty list CTA focuses quick add while completed-only recovers through Store Erledigt',async({page})=>{
  const state=await boot(page,state=>{state.shoppingLists[0].items=[]});await expect(page.getByText('Diese Liste ist noch leer',{exact:true})).toBeVisible();const addFirst=page.getByRole('button',{name:'Ersten Artikel hinzufügen'});const box=await addFirst.boundingBox();expect(box.height).toBeGreaterThanOrEqual(48);await addFirst.click();await expect(page.locator('.smart-input input')).toBeFocused();
  state.shoppingLists[0].items=[{id:'done-1',shopping_list:'shop-1',name:'Schon gekauft',quantity:'1',category:'Vorrat',aisle:'',note:'',favorite:false,checked:true,position:1000,added_by_name:'Alex'}];await page.reload();await expect(page.getByText('Alles erledigt',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Erledigte ansehen'}).click();await expect(page.locator('.store-focus')).toBeVisible();await expect(page.getByRole('button',{name:/^Erledigt 1$/})).toHaveAttribute('aria-pressed','true');await expect(page.getByText('Schon gekauft',{exact:true})).toBeVisible();
});

test('offline is a persistent quiet state and blocks unsupported list creation early',async({page,context})=>{
  await boot(page,()=>{},'en');await context.setOffline(true);await expect(page.getByText('Offline – changes stay saved on this device.',{exact:true})).toBeVisible();await expect(page.getByLabel('Switch shopping list')).toHaveCount(0);await page.getByRole('button',{name:'New list'}).click();await expect(page.getByText('New lists can be created once you are back online.',{exact:true})).toBeVisible();const listNameInput=page.locator('.list-create-panel input');await expect(listNameInput).toBeDisabled();await context.setOffline(false);await expect(page.getByText('Offline – changes stay saved on this device.',{exact:true})).toHaveCount(0);await expect(listNameInput).toBeEnabled();
});

test('offline no-list state explains why creation is unavailable',async({page,context})=>{
  await boot(page,state=>{state.shoppingLists=[]},'en');await context.setOffline(true);await expect(page.getByText('You need a connection briefly to create a new list.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Create shopping list'})).toBeDisabled();
});
