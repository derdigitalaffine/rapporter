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

async function pasteLines(textarea,text){
  await textarea.evaluate((element,value)=>{
    const data=new DataTransfer();
    data.setData('text/plain',value);
    element.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));
  },text);
}

test('Textmodus splits pasted lines, ignores blanks and keeps keyboard entry fast',async({page})=>{
  await bootShopping(page);
  const toggle=page.getByRole('button',{name:'Textmodus'});
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed','true');

  const textarea=page.getByLabel('Artikel zeilenweise hinzufügen');
  await expect(textarea).toBeFocused();
  await pasteLines(textarea,'Bananen\n\nKaffee\r\nÄpfel\n');

  await expect(page.getByLabel('Bananen bearbeiten')).toBeVisible();
  await expect(page.getByLabel('Kaffee bearbeiten')).toBeVisible();
  await expect(page.getByLabel('Äpfel bearbeiten')).toBeVisible();
  await expect(page.locator('.shopping-text-line')).toHaveCount(4);

  await textarea.fill('Tomaten');
  await textarea.press('Enter');
  await expect(page.getByLabel('Tomaten bearbeiten')).toBeVisible();
  await expect(textarea).toBeFocused();
  await expect(textarea).toHaveValue('');
});

test('Textmodus renames and removes existing rows without losing shopping metadata or store mode',async({page})=>{
  const requests=[];
  page.on('request',request=>{if(request.url().includes('/api/shopping-items/'))requests.push({method:request.method(),url:request.url(),body:request.postData()})});
  await bootShopping(page);
  await page.getByRole('button',{name:'Textmodus'}).click();

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
  await expect(page.getByLabel('Artikel zeilenweise hinzufügen')).toHaveCount(0);
  await expect(page.locator('.store-focus')).toBeVisible();
  const noHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1);
  expect(noHorizontalOverflow).toBe(true);
});
