import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page){const state=await installApiMocks(page,{dismissOnboarding:true});await page.goto('/');await page.waitForLoadState('networkidle');await page.locator('.bottom-nav').getByRole('button',{name:'Einkauf'}).click();await expect(page.getByText('Milch',{exact:true})).toBeVisible();return state}

test('shopping add, check, edit and favorite survive offline reload and sync once after reconnect',async({page,context})=>{
  const state=await boot(page);
  await context.setOffline(true);

  const quick=page.locator('.smart-input input');
  await quick.fill('Brot offline');
  await quick.press('Enter');
  const bread=page.locator('.shopping-row').filter({hasText:'Brot offline'});
  await expect(bread).toBeVisible();
  await expect(bread.getByText('Noch nicht synchronisiert')).toBeVisible();

  await bread.locator('.row-main-button').click();
  const editor=page.getByRole('dialog');
  await editor.getByLabel('Menge').fill('2');
  await editor.getByRole('button',{name:'Speichern',exact:true}).click();
  await expect(bread.getByText('2',{exact:true})).toBeVisible();
  await bread.locator('.row-action').click();

  await page.getByRole('button',{name:/Im Laden/i}).click();
  const milk=page.locator('.shopping-row').filter({hasText:'Milch'});
  await milk.locator('.smart-check').click();
  await expect(page.getByText(/1 von 2|1\/2/)).toBeVisible();
  await expect(page.getByText(/Offline – Änderungen werden lokal gespeichert/)).toBeVisible();

  await page.reload();
  await page.waitForLoadState('domcontentloaded');
  await expect(page.getByText('Brot offline',{exact:true})).toBeVisible();
  await expect(page.getByText(/Offline – Änderungen werden lokal gespeichert/)).toBeVisible();

  await context.setOffline(false);
  await expect(page.locator('.shopping-offline-status')).toHaveCount(0,{timeout:10000});
  await expect.poll(()=>state.shoppingLists[0].items.filter(item=>item.name==='Brot offline').length).toBe(1);
  const syncedBread=state.shoppingLists[0].items.find(item=>item.name==='Brot offline');
  const syncedMilk=state.shoppingLists[0].items.find(item=>item.name==='Milch');
  expect(syncedBread.quantity).toBe('2');
  expect(syncedBread.favorite).toBe(true);
  expect(syncedMilk.checked).toBe(true);
});
