import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('uses FamilyOS across document, login and app chrome',async({page})=>{
 await installApiMocks(page,{authenticated:false});
 await page.goto('/');
 await expect(page).toHaveTitle('FamilyOS');
 await expect(page.locator('img.brand-wide')).toHaveAttribute('alt','FamilyOS');
 await expect(page.getByText('fam-uh-le',{exact:true})).toHaveCount(0);
});

test('installed manifest is branded FamilyOS',async({request})=>{
 const response=await request.get('/manifest.webmanifest');
 expect(response.ok()).toBeTruthy();
 const manifest=await response.json();
 expect(manifest.name).toBe('FamilyOS');
 expect(manifest.short_name).toBe('FamilyOS');
});
