import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('FamilyOS calendar detail and editor render outside the app scroll container',async({page})=>{
  await page.setViewportSize({width:390,height:640});
  await page.addInitScript(()=>document.documentElement.setAttribute('data-app-standalone','true'));
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto('/?page=calendar&view=list');
  await page.waitForLoadState('networkidle');

  const row=page.locator('.agenda-event').filter({hasText:'Kinderarzt'}).first();
  await expect(row).toBeVisible();
  await row.click();

  const detail=page.getByRole('dialog').filter({hasText:'Kinderarzt'});
  await expect(detail).toBeVisible();
  expect(await detail.evaluate(node=>Boolean(node.closest('.content')))).toBe(false);
  await expect(page.locator('body > .sheet-backdrop').filter({has:detail})).toBeVisible();

  const editButton=detail.getByRole('button',{name:'Termin bearbeiten',exact:true});
  await expect(editButton).toBeVisible();
  await editButton.click();

  const editor=page.getByRole('dialog',{name:'Termin bearbeiten'});
  await expect(editor).toBeVisible();
  expect(await editor.evaluate(node=>Boolean(node.closest('.content')))).toBe(false);
  await expect(page.locator('body > .sheet-backdrop').filter({has:editor})).toBeVisible();
});
