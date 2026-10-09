import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page){
  const state=await installApiMocks(page,{dismissOnboarding:true});
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.locator('.bottom-nav').getByRole('button',{name:'Einkauf'}).click();
  await expect(page.getByText('Milch',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Textmodus'}).click();
  await expect(page.getByRole('textbox',{name:'Artikel zeilenweise hinzufügen'})).toBeFocused();
  return state;
}

test('multiline shopping text adds every non-empty line in one flow and syncs after reconnect',async({page,context})=>{
  const state=await boot(page);
  const textarea=page.getByRole('textbox',{name:'Artikel zeilenweise hinzufügen'});
  await context.setOffline(true);
  await textarea.fill('Brot\n\nÄpfel\n   \nKaffee');
  await page.getByRole('button',{name:'Zeilen hinzufügen'}).click();

  await expect(page.getByRole('textbox',{name:'Brot bearbeiten'})).toBeVisible();
  await expect(page.getByRole('textbox',{name:'Äpfel bearbeiten'})).toBeVisible();
  await expect(page.getByRole('textbox',{name:'Kaffee bearbeiten'})).toBeVisible();
  await expect(textarea).toHaveValue('');
  await expect(textarea).toBeFocused();
  await expect(page.locator('.shopping-text-line')).toHaveCount(4);
  await expect(page.getByText(/Offline – Änderungen werden lokal gespeichert/)).toBeVisible();

  await context.setOffline(false);
  await expect(page.locator('.shopping-offline-status')).toHaveCount(0,{timeout:10000});
  await expect.poll(()=>state.shoppingLists[0].items.map(item=>item.name).filter(name=>['Brot','Äpfel','Kaffee'].includes(name)).length).toBe(3);
  expect(state.shoppingLists[0].items.some(item=>!item.name.trim())).toBe(false);
});

test('existing shopping lines rename and remove quickly while preserving metadata',async({page})=>{
  const state=await boot(page);
  const milk=page.getByRole('textbox',{name:'Milch bearbeiten'});
  await expect(page.getByText('1 l · Kühlung · Kühlregal',{exact:true})).toBeVisible();

  await milk.fill('Hafermilch');
  await milk.press('Enter');
  await expect(page.getByRole('textbox',{name:'Hafermilch bearbeiten'})).toBeVisible();
  await expect(page.getByText('1 l · Kühlung · Kühlregal',{exact:true})).toBeVisible();
  await expect.poll(()=>state.shoppingLists[0].items.find(item=>item.id==='item-1')?.name).toBe('Hafermilch');
  const renamed=state.shoppingLists[0].items.find(item=>item.id==='item-1');
  expect(renamed.quantity).toBe('1 l');
  expect(renamed.category).toBe('Kühlung');
  expect(renamed.aisle).toBe('Kühlregal');

  await page.getByRole('button',{name:'Hafermilch entfernen'}).click();
  await expect(page.getByRole('textbox',{name:'Hafermilch bearbeiten'})).toHaveCount(0);
  await expect.poll(()=>state.shoppingLists[0].items.some(item=>item.id==='item-1')).toBe(false);
});

test('mobile text mode keeps touch targets and keyboard-safe font sizing',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await boot(page);
  const textarea=page.getByRole('textbox',{name:'Artikel zeilenweise hinzufügen'});
  const remove=page.getByRole('button',{name:'Milch entfernen'});
  const metrics=await page.evaluate(()=>({
    overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
    textareaFont:parseFloat(getComputedStyle(document.querySelector('#shopping-text-input')).fontSize),
  }));
  const removeBox=await remove.boundingBox();
  expect(metrics.overflow).toBeLessThanOrEqual(1);
  expect(metrics.textareaFont).toBeGreaterThanOrEqual(16);
  expect(removeBox.width).toBeGreaterThanOrEqual(44);
  expect(removeBox.height).toBeGreaterThanOrEqual(44);
  await textarea.fill('Birnen');
  await textarea.press('Enter');
  await expect(page.getByRole('textbox',{name:'Birnen bearbeiten'})).toBeVisible();
  await expect(textarea).toBeFocused();
});
