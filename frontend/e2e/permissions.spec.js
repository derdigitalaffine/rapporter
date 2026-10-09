import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const familyId='family-1';

async function sessionAs(page,user){
 await page.route('**/api/auth/session/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({authenticated:true,user})}));
}

async function familyAsTeen(page){
 const memberships=[{id:'member-3',family:familyId,user:3,username:'taylor',role:'teen',display_name:'Taylor',avatar:''}];
 const family={id:familyId,name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships};
 await page.route('**/api/families/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([family])}));
}

async function open(page,path){
 await page.goto(path);
 await page.waitForLoadState('networkidle');
}

test('adult can manage integrations and automations',async({page})=>{
 await installApiMocks(page);
 await sessionAs(page,{id:2,username:'sam',email:'sam@example.test'});
 await open(page,'/?page=integrations');
 await expect(page.getByRole('button',{name:'Erneut versuchen'})).toBeVisible();
 await expect(page.getByText('Du kannst Integrationen ansehen.')).toHaveCount(0);

 await open(page,'/?page=automations');
 await expect(page.locator('.automation-template').first()).toBeVisible();
 await expect(page.getByText('Du kannst Regeln und ihren Status ansehen.')).toHaveCount(0);
});

test('teen gets read-only integrations and automations on direct links',async({page})=>{
 await installApiMocks(page);
 await sessionAs(page,{id:3,username:'taylor',email:'taylor@example.test'});
 await familyAsTeen(page);

 await open(page,'/?page=integrations');
 await expect(page.getByText(/Du kannst Integrationen ansehen/)).toBeVisible();
 await expect(page.getByRole('button',{name:'Erneut versuchen'})).toHaveCount(0);
 await expect(page.locator('.catalog-actions button')).toHaveCount(0);
 await expect(page.getByText('Nur ansehen').first()).toBeVisible();

 await open(page,'/?page=automations');
 await expect(page.getByText(/Du kannst Regeln und ihren Status ansehen/)).toBeVisible();
 await expect(page.locator('.automation-template')).toHaveCount(0);
 await expect(page.locator('.automation-builder')).toHaveCount(0);
 await expect(page.locator('.rule-actions')).toHaveCount(0);
});
