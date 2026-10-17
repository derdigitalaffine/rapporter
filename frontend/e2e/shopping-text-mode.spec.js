import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function bootShopping(page){
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.locator('.bottom-nav').getByRole('button',{name:'Einkauf'}).click();
  await expect(page.getByRole('heading',{name:'Einkauf',exact:true})).toBeVisible();
}

async function openTextMode(page){
  await page.locator('.shopping-overflow > summary').click();
  const toggle=page.getByRole('button',{name:'Textmodus'});
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed','true');
}

test('Textmodus keeps multiline input as draft until explicit apply',async({page})=>{
  const creates=[];
  page.on('request',request=>{
    if(request.method()==='POST'&&request.url().includes('/api/smart/shopping/quick-add/')){
      let body={};try{body=request.postDataJSON()||{}}catch{}
      creates.push(body);
    }
  });

  await bootShopping(page);
  await openTextMode(page);

  const textarea=page.getByLabel('Artikel zeilenweise erfassen');
  await textarea.fill('2 x Bananen\n500 g Tomaten\n\nKaffee');

  const preview=page.getByLabel('Vorschau');
  await expect(preview).toBeVisible();
  await expect(preview.locator('.shopping-text-preview-row')).toHaveCount(3);
  await expect(preview).toContainText('3 Zeilen');
  expect(creates).toHaveLength(0);

  const firstName=preview.locator('.shopping-text-preview-row').first().getByLabel('Artikel');
  await expect(firstName).toHaveValue(/Bananen/);
  await firstName.fill('Bio-Bananen');

  await textarea.press('End');
  await textarea.press('Enter');
  expect(creates).toHaveLength(0);

  await page.getByRole('button',{name:'Übernehmen'}).click();

  await expect(textarea).toHaveValue('');
  await expect.poll(()=>creates.length).toBe(3);
  expect(creates[0].name).toBe('Bio-Bananen');
  expect(creates[0].client_mutation_id).toMatch(/^[0-9a-f-]{36}$/i);
  await expect(page.getByLabel('Bio-Bananen bearbeiten')).toBeVisible();
});

test('Textmodus renames and removes existing rows without losing shopping metadata or store mode',async({page})=>{
  const requests=[];
  page.on('request',request=>{if(request.url().includes('/api/shopping-items/'))requests.push({method:request.method(),url:request.url(),body:request.postData()})});
  await bootShopping(page);
  await openTextMode(page);

  const milk=page.getByLabel('Milch bearbeiten');
  await milk.fill('Hafermilch');
  await milk.press('Enter');
  await expect(page.getByLabel('Hafermilch bearbeiten')).toBeVisible();
  await expect(page.locator('.shopping-text-line').filter({has:page.getByLabel('Hafermilch bearbeiten')})).toContainText('1 l');

  await page.getByLabel('Hafermilch entfernen').click();
  await expect(page.getByLabel('Hafermilch bearbeiten')).toHaveCount(0);

  await expect.poll(()=>requests.some(request=>request.method==='PATCH'&&request.body?.includes('Hafermilch'))).toBe(true);
  await expect.poll(()=>requests.some(request=>request.method==='DELETE')).toBe(true);

  await page.getByRole('button',{name:'Im Laden'}).click();
  await expect(page.getByLabel('Artikel zeilenweise erfassen')).toHaveCount(0);
  await expect(page.locator('.store-focus')).toBeVisible();
  const noHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1);
  expect(noHorizontalOverflow).toBe(true);
});