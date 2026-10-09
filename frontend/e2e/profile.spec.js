import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');

async function installProfileMock(page){
 let profile={user_id:1,username:'alex',email:'alex@example.test',avatar_url:'',birth_month:3,birth_day:12,birth_year:null,family:'family-1',membership_id:'member-1',display_name:'Alex',role:'owner',birthday_visibility:'day_month'};
 await page.route('**/api/profile/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname;const method=request.method();
  if(/^\/api\/profile\/avatar\/1\/(64|128|256)\/$/.test(path)&&method==='GET')return route.fulfill({status:200,contentType:'image/png',body:png});
  if(path==='/api/profile/avatar/'&&method==='POST'){profile={...profile,avatar_url:'/api/profile/avatar/1/256/?v=test'};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(profile)})}
  if(path==='/api/profile/avatar/'&&method==='DELETE'){profile={...profile,avatar_url:''};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(profile)})}
  if(path==='/api/profile/'&&method==='PATCH'){const body=request.postDataJSON();profile={...profile,...body,birth_month:body.birth_month??null,birth_day:body.birth_day??null,birth_year:body.birth_year??null};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(profile)})}
  if(path==='/api/profile/'&&method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(profile)});
  return route.fallback();
 });
 return()=>profile;
}

test('profile is reachable from More and survives reload',async({page})=>{
 await installApiMocks(page);
 await installProfileMock(page);
 await page.goto('/?page=more');
 await page.locator('main .menu-row').filter({hasText:'Mein Profil'}).click();
 await expect(page).toHaveURL(/page=profile/);
 await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();
 await page.reload();
 await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();
});

test('user updates family name birthday and visibility without changing role',async({page})=>{
 await installApiMocks(page);
 const current=await installProfileMock(page);
 await page.goto('/?page=profile');
 await page.getByLabel('Name in dieser Familie').fill('Alex Familie');
 await page.getByLabel('Tag').fill('29');
 await page.getByLabel('Monat').fill('2');
 await page.getByLabel(/Jahr/).fill('2000');
 await page.getByLabel(/Wer darf meinen Geburtstag/).selectOption('full_date');
 await page.getByRole('button',{name:'Speichern'}).click();
 await expect(page.getByText('Profil gespeichert.')).toBeVisible();
 expect(current().display_name).toBe('Alex Familie');
 expect(current().birth_day).toBe(29);
 expect(current().birth_month).toBe(2);
 expect(current().birth_year).toBe(2000);
 expect(current().birthday_visibility).toBe('full_date');
 expect(current().role).toBe('owner');
});

test('avatar upload and removal update the profile immediately',async({page})=>{
 await installApiMocks(page);
 await installProfileMock(page);
 await page.goto('/?page=profile');
 await page.locator('input[type=file]').first().setInputFiles({name:'portrait.png',mimeType:'image/png',buffer:png});
 await expect(page.locator('.profile-hero img')).toBeVisible();
 await page.getByRole('button',{name:'Entfernen'}).click();
 await expect(page.locator('.profile-hero img')).toHaveCount(0);
 await expect(page.getByText('Profilfoto entfernt.')).toBeVisible();
});

test('profile has no horizontal overflow on phone tablet and desktop',async({page})=>{
 await installApiMocks(page);
 await installProfileMock(page);
 for(const size of [{width:390,height:844},{width:1024,height:768},{width:1440,height:900}]){
  await page.setViewportSize(size);
  await page.goto('/?page=profile');
  await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 }
});
