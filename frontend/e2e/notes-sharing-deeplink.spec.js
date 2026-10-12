import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';


test('canonical note share deep link opens the owner sharing panel',async({page})=>{
 await installApiMocks(page,{language:'de'});
 const note={id:'note-share-1',family:'family-1',author:1,title:'Private Notiz',body:'',drawing:[],shares:[],pinned:false,extended_mode:false,blocks:[],version:1,permission:'owner'};
 await page.route('**/api/notes/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(route.request().method()!=='GET')return route.fulfill({status:405,json:{detail:'method_not_allowed'}});
  if(path==='/api/notes/')return route.fulfill({json:{results:[note],next:null}});
  if(path==='/api/notes/note-share-1/')return route.fulfill({json:note});
  return route.fulfill({status:404,json:{detail:'not_found'}});
 });
 await page.goto('/?page=notes&note=note-share-1&share=1');
 await expect(page.getByRole('heading',{name:'Freigaben',exact:true})).toBeVisible();
 await expect(page.locator('.note-sharing')).toBeVisible();
 await expect(page).toHaveURL(/share=1/);
});
