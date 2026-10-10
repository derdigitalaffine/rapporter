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

async function installFamilyMasterMock(page,state){
 const role=()=>state.memberships.find(row=>row.user===1)?.role||'guest';
 let master={family:'family-1',name:state.family.name,slug:state.family.slug,can_edit:role()==='owner',image_url:'',address_street:'',address_house_number:'',address_postal_code:'',address_city:'',address_region:'',address_country_code:'',location_context:{source:'family_address',address:{street:'',house_number:'',postal_code:'',city:'',region:'',country_code:''},has_address:false,ready_for_geocoding:false,coordinates:null}};
 const payload=()=>({...master,can_edit:role()==='owner'});
 await page.route('**/api/family-settings/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname;const method=request.method();
  if(path==='/api/family-settings/image/family-1/'&&method==='GET')return route.fulfill({status:200,contentType:'image/png',body:png});
  if(path==='/api/family-settings/'&&method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload())});
  if(path==='/api/family-settings/'&&method==='PATCH'){
   if(role()!=='owner')return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({detail:'forbidden'})});
   const body=request.postDataJSON();master={...master,...body,address_country_code:(body.address_country_code||master.address_country_code).toUpperCase()};state.family.name=master.name;master.location_context={source:'family_address',address:{street:master.address_street,house_number:master.address_house_number,postal_code:master.address_postal_code,city:master.address_city,region:master.address_region,country_code:master.address_country_code},has_address:Boolean(master.address_city||master.address_postal_code||master.address_street),ready_for_geocoding:Boolean(master.address_city&&master.address_country_code),coordinates:null};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload())});
  }
  if(path==='/api/family-settings/image/'&&method==='POST'){
   if(role()!=='owner')return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({detail:'forbidden'})});
   master={...master,image_url:'/api/family-settings/image/family-1/?v=test'};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload())});
  }
  if(path==='/api/family-settings/image/'&&method==='DELETE'){
   if(role()!=='owner')return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({detail:'forbidden'})});
   master={...master,image_url:''};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload())});
  }
  return route.fallback();
 });
 return()=>payload();
}

test('profile is reachable from More and survives reload',async({page})=>{
 const state=await installApiMocks(page);
 await installProfileMock(page);await installFamilyMasterMock(page,state);
 await page.goto('/?page=more');
 await page.locator('main .menu-row').filter({hasText:'Mein Profil'}).click();
 await expect(page).toHaveURL(/page=profile/);
 await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();
 await page.reload();
 await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();
});

test('user updates profile name birthday and visibility without changing role',async({page})=>{
 const state=await installApiMocks(page);
 const current=await installProfileMock(page);await installFamilyMasterMock(page,state);
 await page.goto('/?page=profile');
 await page.getByLabel('Name in dieser Familie').fill('Alex Familie');
 await page.getByRole('spinbutton',{name:'Tag',exact:true}).fill('29');
 await page.getByRole('spinbutton',{name:'Monat',exact:true}).fill('2');
 await page.getByRole('spinbutton',{name:/^Jahr/}).fill('2000');
 await page.getByLabel(/Wer darf meinen Geburtstag/).selectOption('full_date');
 await page.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect(page.getByText('Profil gespeichert.')).toBeVisible();
 expect(current().display_name).toBe('Alex Familie');
 expect(current().birth_day).toBe(29);
 expect(current().birth_month).toBe(2);
 expect(current().birth_year).toBe(2000);
 expect(current().birthday_visibility).toBe('full_date');
 expect(current().role).toBe('owner');
});

test('avatar upload and removal update the profile immediately',async({page})=>{
 const state=await installApiMocks(page);
 await installProfileMock(page);await installFamilyMasterMock(page,state);
 await page.goto('/?page=profile');
 await page.locator('input[type=file]').first().setInputFiles({name:'portrait.png',mimeType:'image/png',buffer:png});
 await expect(page.locator('.profile-hero img')).toBeVisible();
 await page.getByRole('button',{name:'Entfernen',exact:true}).click();
 await expect(page.locator('.profile-hero img')).toHaveCount(0);
 await expect(page.getByText('Profilfoto entfernt.')).toBeVisible();
});

test('owner edits family name and address while technical slug stays stable',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);const current=await installFamilyMasterMock(page,state);
 await page.goto('/?page=profile');
 const section=page.getByTestId('family-master-data');
 await section.getByLabel('Familienname').fill('Familie Sonnenschein');
 await section.getByLabel('Straße').fill('Musterstraße');
 await section.getByLabel('Hausnummer').fill('12a');
 await section.getByLabel('PLZ').fill('67655');
 await section.getByLabel('Ort').fill('Kaiserslautern');
 await section.getByLabel('Bundesland / Region').fill('Rheinland-Pfalz');
 await section.getByLabel('Ländercode').fill('de');
 await section.getByRole('button',{name:'Familienstammdaten speichern'}).click();
 await expect(page.getByText('Familienstammdaten gespeichert.')).toBeVisible();
 await expect(page.locator('.page-head small')).toContainText('Familie Sonnenschein');
 expect(current().name).toBe('Familie Sonnenschein');expect(current().slug).toBe('musterfamilie');expect(current().address_city).toBe('Kaiserslautern');expect(current().address_country_code).toBe('DE');expect(current().location_context.coordinates).toBeNull();
 await page.reload();
 await expect(section.getByLabel('Familienname')).toHaveValue('Familie Sonnenschein');
 await expect(section.getByLabel('Ort')).toHaveValue('Kaiserslautern');
 await expect(section.getByText('musterfamilie',{exact:true})).toBeVisible();
});

test('owner uploads and removes private family image',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);await installFamilyMasterMock(page,state);
 await page.goto('/?page=profile');
 const section=page.getByTestId('family-master-data');
 await section.locator('input[type=file]').setInputFiles({name:'family.png',mimeType:'image/png',buffer:png});
 await expect(section.locator('img.family-master-image')).toBeVisible();
 await expect(page.getByText('Familienbild aktualisiert.')).toBeVisible();
 await section.getByRole('button',{name:'Familienbild entfernen'}).click();
 await expect(section.locator('img.family-master-image')).toHaveCount(0);
 await expect(page.getByText('Familienbild entfernt.')).toBeVisible();
});

test('non-owner sees family master data read-only',async({page})=>{
 const state=await installApiMocks(page);state.memberships[0].role='adult';await installProfileMock(page);await installFamilyMasterMock(page,state);
 await page.goto('/?page=profile');
 const section=page.getByTestId('family-master-data');
 await expect(section.getByText('Diese Stammdaten können nur vom Owner geändert werden.')).toBeVisible();
 await expect(section.getByLabel('Familienname')).toBeDisabled();
 await expect(section.getByLabel('Ort')).toBeDisabled();
 await expect(section.getByRole('button',{name:'Familienstammdaten speichern'})).toHaveCount(0);
 await expect(section.locator('input[type=file]')).toHaveCount(0);
});

test('profile and family master data have no horizontal overflow on phone tablet and desktop',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);await installFamilyMasterMock(page,state);
 for(const size of [{width:390,height:844},{width:1024,height:768},{width:1440,height:900}]){
  await page.setViewportSize(size);
  await page.goto('/?page=profile');
  await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();
  await expect(page.getByTestId('family-master-data')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 }
});
