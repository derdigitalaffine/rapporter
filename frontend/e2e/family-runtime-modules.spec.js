import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('app shell module responses feed global create without duplicate module requests',async({page})=>{
 const counts={baby:0,pets:0};
 page.on('request',request=>{
  const url=new URL(request.url());
  if(url.pathname==='/api/baby/module/')counts.baby+=1;
  if(url.pathname==='/api/pets/module/')counts.pets+=1;
 });
 await installApiMocks(page,{dismissOnboarding:true});
 await page.goto('/');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.today-hero h1')).toBeVisible();
 await expect(page.locator('.global-create-fab')).toBeVisible();
 expect(counts).toEqual({baby:1,pets:1});
});
