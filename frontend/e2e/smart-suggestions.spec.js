import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,path){
  await installApiMocks(page);
  await page.goto(path);
  await page.waitForLoadState('networkidle');
}

test('remembered task suggestion adds immediately with learned defaults',async({page})=>{
  await page.route('**/api/tasks/suggestions/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([{name:'Pflanzen gießen',notes:'Wohnzimmer zuerst',priority:'high',estimate_minutes:15,count:6}])}));
  let creates=0;
  page.on('request',request=>{if(new URL(request.url()).pathname==='/api/smart/tasks/quick-add/')creates+=1});
  await boot(page,'/?page=tasks');
  const input=page.locator('.smart-input input');
  await input.focus();
  const suggestion=page.getByRole('button',{name:'Pflanzen gießen · Hinzufügen'});
  await expect(suggestion).toBeVisible();
  await suggestion.click();
  const row=page.locator('.smart-row').filter({hasText:'Pflanzen gießen'});
  await expect(row).toBeVisible();
  await expect(row).toContainText('Wichtig');
  await expect(row).toContainText('15 min');
  await expect(input).toHaveValue('');
  expect(creates).toBe(1);
});

test('remembered shopping suggestion adds immediately with learned defaults',async({page})=>{
  await page.route('**/api/shopping-items/suggestions/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([{name:'Hafermilch',quantity:'2 l',category:'Kühlung',aisle:'Kühlregal',note:'Barista',count:4}])}));
  await boot(page,'/?page=shopping');
  const input=page.locator('.smart-input input').first();
  await input.focus();
  const suggestion=page.getByRole('button',{name:'Hafermilch · Hinzufügen'});
  await expect(suggestion).toBeVisible();
  await suggestion.click();
  const row=page.locator('.smart-row').filter({hasText:'Hafermilch'});
  await expect(row).toBeVisible();
  await expect(row).toContainText('2 l');
  await expect(row).toContainText('Kühlregal');
  await expect(input).toHaveValue('');
});
