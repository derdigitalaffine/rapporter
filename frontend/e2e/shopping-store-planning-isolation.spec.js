import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('store · planning and budget surfaces stay unmounted and do not load planning data',async({page})=>{
 const planningRequests=[];
 page.on('request',request=>{
  if(request.method()!=='GET')return;
  const {pathname}=new URL(request.url());
  if(
   pathname==='/api/shopping-predictions/'||
   pathname==='/api/expense-ledgers/'||
   pathname==='/api/expense-budgets/'||
   pathname.startsWith('/api/budget-commitments/source/shopping_item/')
  )planningRequests.push(pathname);
 });
 await installApiMocks(page,{dismissOnboarding:true});
 await page.setViewportSize({width:390,height:844});
 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');

 await expect(page.locator('.store-focus')).toBeVisible();
 await expect(page.locator('.shopping-predictions')).toHaveCount(0);
 await expect(page.locator('.shopping-budget-commitment')).toHaveCount(0);
 expect(planningRequests).toEqual([]);
});
