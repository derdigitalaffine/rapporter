import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const widgetIds=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes','loyalty','inbox'];

test('Today surfaces accessible loyalty cards and unread family inbox',async({page})=>{
  await installApiMocks(page);
  await page.route('**/api/today-layout/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,revision:0,widgets:widgetIds.map(id=>({id,visible:true,size:'full'}))})}));
  await page.route('**/api/inbox/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([{id:'message-1',family:'family-1',status:'new',title:'Familieninfo'}])}));
  await page.route('**/api/loyalty-cards/sync/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([{id:'card-1',family:'family-1',name:'REWE Bonus',favorite:true,holder_display:'Alex',barcode_format:'code128',barcode_value:'123456789',customer_number:'123456789',can_edit:true}])}));
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('today-loyalty')).toContainText('REWE Bonus');
  await expect(page.getByTestId('today-inbox')).toContainText('1 ungelesen');
  await Promise.all([
    page.waitForURL(/page=loyalty/),
    page.getByRole('button',{name:'REWE Bonus · Bonuskarten'}).click(),
  ]);
  await expect(page.getByRole('dialog').getByRole('heading',{name:'REWE Bonus'})).toBeVisible();
});
