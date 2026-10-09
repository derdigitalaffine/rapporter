import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

test('superadmin creates a separated family and owner invitation',async({page})=>{
 await installApiMocks(page);page.on('dialog',dialog=>dialog.dismiss());
 let families=[];
 await page.route('**/api/auth/session/',route=>json(route,{authenticated:true,user:{id:99,username:'root',email:'root@example.test',is_superadmin:true}}));
 await page.route('**/api/superadmin/families/**',async route=>{
  const url=new URL(route.request().url());const method=route.request().method();
  if(url.pathname==='/api/superadmin/families/'&&method==='GET')return json(route,families);
  if(url.pathname==='/api/superadmin/families/'&&method==='POST'){
   const body=route.request().postDataJSON();const family={id:'tenant-2',name:body.name,slug:'familie-zwei',locale:body.locale,timezone:body.timezone,status:'active',member_count:0,owners:[],pending_owner_invites:[{token:'invite-owner'}]};families=[family];return json(route,{family,invite_token:'invite-owner'},201);
  }
  return json(route,{detail:'not found'},404);
 });
 await page.goto('/');
 await expect(page.getByText('Superadmin')).toBeVisible();
 await expect(page.getByRole('heading',{name:'Familien sicher getrennt verwalten'})).toBeVisible();
 await page.getByLabel('Familienname').fill('Familie Zwei');
 await page.getByLabel('Owner-Name').fill('Pat');
 await page.getByLabel('Owner-E-Mail').fill('pat@example.test');
 await page.getByRole('button',{name:/Familie anlegen/}).click();
 await expect(page.getByRole('heading',{name:'Familie Zwei'})).toBeVisible();
 await expect(page.getByText('Noch kein Owner registriert')).toBeVisible();
 await expect(page.getByText(/offene Owner-Einladung/)).toBeVisible();
});
