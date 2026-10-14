import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');

async function installProfileMock(page){
 let profile={user_id:1,username:'alex',email:'alex@example.test',avatar_url:'',birth_month:3,birth_day:12,birth_year:null,family:'family-1',membership_id:'member-1',display_name:'Alex',role:'owner',birthday_visibility:'day_month',show_birthday_age:true,calendar_color:'#4f7cff',calendar_color_palette:['#4f7cff','#eb6f92','#3aa981']};
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

async function openFamilyMaster(page){const section=page.getByTestId('family-master-data');await expect(section).toBeVisible();if(!(await section.evaluate(node=>node.open)))await section.locator('summary').click();return section}

test('profile is reachable from More and survives reload',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);await installFamilyMasterMock(page,state);
 await page.goto('/?page=more');await page.locator('main .menu-row').filter({hasText:'Mein Profil'}).click();await expect(page).toHaveURL(/page=profile/);await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();await page.reload();await expect(page.getByRole('heading',{name:'Mein Profil'})).toBeVisible();
});

test('user updates profile name birthday and visibility without changing role',async({page})=>{
 const state=await installApiMocks(page);const current=await installProfileMock(page);await installFamilyMasterMock(page,state);await page.goto('/?page=profile');await page.getByLabel('Name in dieser Familie').fill('Alex Familie');await page.getByRole('spinbutton',{name:'Tag',exact:true}).fill('29');await page.getByRole('spinbutton',{name:'Monat',exact:true}).fill('2');await page.getByRole('spinbutton',{name:/^Jahr/}).fill('2000');await page.getByLabel(/Wer darf meinen Geburtstag/).selectOption('full_date');await page.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.getByText('Profil gespeichert.')).toBeVisible();expect(current().display_name).toBe('Alex Familie');expect(current().birth_day).toBe(29);expect(current().birth_month).toBe(2);expect(current().birth_year).toBe(2000);expect(current().birthday_visibility).toBe('full_date');expect(current().role).toBe('owner');
});

test('avatar upload opens adjustable crop before saving and removal updates immediately',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);await installFamilyMasterMock(page,state);await page.goto('/?page=profile');await page.locator('.profile-hero input[type=file]').first().setInputFiles({name:'portrait.png',mimeType:'image/png',buffer:png});
 const cropper=page.locator('.profile-cropper-sheet');await expect(cropper.getByRole('heading',{name:'Bildausschnitt einstellen'})).toBeVisible();await expect(page.locator('.profile-hero img')).toHaveCount(0);
 const zoom=cropper.locator('input[type=range]');await zoom.fill('2');const image=cropper.locator('.profile-cropper-stage img');const before=await image.getAttribute('style');const stage=cropper.locator('.profile-cropper-stage');const box=await stage.boundingBox();if(box){await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+24,box.y+box.height/2+18);await page.mouse.up()}const after=await image.getAttribute('style');expect(after).not.toBe(before);
 await cropper.getByRole('button',{name:'Ausschnitt verwenden'}).click();await expect(cropper).toHaveCount(0);await expect(page.locator('.profile-hero img')).toBeVisible();await expect(page.getByText('Profilfoto aktualisiert.')).toBeVisible();await page.getByRole('button',{name:'Entfernen',exact:true}).click();await expect(page.locator('.profile-hero img')).toHaveCount(0);await expect(page.getByText('Profilfoto entfernt.')).toBeVisible();
});

test('profile keeps personal settings primary and collapses account security and quick actions',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);await installFamilyMasterMock(page,state);await page.goto('/?page=profile');await expect(page.getByLabel('Name in dieser Familie')).toBeVisible();await expect(page.getByTestId('family-master-data')).toHaveCount(0);
 for(const title of ['Konto & E-Mail','Sicherheit & Sitzungen','Schnellaktionen']){const details=page.locator('details.profile-disclosure').filter({hasText:title});await expect(details).toBeVisible();expect(await details.evaluate(node=>node.open)).toBe(false)}
});

test('owner edits family master data on family management page',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);const current=await installFamilyMasterMock(page,state);await page.goto('/?page=members');const section=await openFamilyMaster(page);await section.getByLabel('Familienname').fill('Familie Sonnenschein');await section.getByLabel('Straße').fill('Musterstraße');await section.getByLabel('Hausnummer').fill('12a');await section.getByLabel('PLZ').fill('67655');await section.getByLabel('Ort').fill('Kaiserslautern');await section.getByLabel('Bundesland / Region').fill('Rheinland-Pfalz');await section.getByLabel('Ländercode').fill('de');await section.getByRole('button',{name:'Familienstammdaten speichern'}).click();await expect(page.getByText('Familienstammdaten gespeichert.')).toBeVisible();await expect(page.locator('.page-head small')).toContainText('Familie Sonnenschein');expect(current().name).toBe('Familie Sonnenschein');expect(current().slug).toBe('musterfamilie');expect(current().address_city).toBe('Kaiserslautern');expect(current().address_country_code).toBe('DE');
});

test('owner uploads and removes private family image from family management',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);await installFamilyMasterMock(page,state);await page.goto('/?page=members');const section=await openFamilyMaster(page);await section.locator('input[type=file]').setInputFiles({name:'family.png',mimeType:'image/png',buffer:png});await expect(section.locator('img.family-master-image')).toBeVisible();await expect(page.getByText('Familienbild aktualisiert.')).toBeVisible();await section.getByRole('button',{name:'Familienbild entfernen'}).click();await expect(section.locator('img.family-master-image')).toHaveCount(0);await expect(page.getByText('Familienbild entfernt.')).toBeVisible();
});

test('non-owner sees family master data read-only on family management page',async({page})=>{
 const state=await installApiMocks(page);state.memberships[0].role='adult';await installProfileMock(page);await installFamilyMasterMock(page,state);await page.goto('/?page=members');const section=await openFamilyMaster(page);await expect(section.getByText('Diese Stammdaten können nur vom Owner geändert werden.').first()).toBeVisible();await expect(section.getByLabel('Familienname')).toBeDisabled();await expect(section.getByLabel('Ort')).toBeDisabled();await expect(section.getByRole('button',{name:'Familienstammdaten speichern'})).toHaveCount(0);await expect(section.locator('input[type=file]')).toHaveCount(0);
});

test('profile and family management have no horizontal overflow on phone tablet and desktop',async({page})=>{
 const state=await installApiMocks(page);await installProfileMock(page);await installFamilyMasterMock(page,state);for(const size of [{width:390,height:844},{width:1024,height:768},{width:1440,height:900}]){await page.setViewportSize(size);for(const target of ['profile','members']){await page.goto(`/?page=${target}`);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true)}}
});

test('profile · HEIC original can be uploaded when crop preview is unsupported',async({page})=>{
 await installApiMocks(page);await installProfileMock(page);
 // Model an unsupported browser decoder while retaining a real HEIC payload
 // for the upload. HEIC decoding/validation is exercised by backend tests.
 await page.addInitScript(()=>{const create=URL.createObjectURL.bind(URL);URL.createObjectURL=blob=>blob instanceof File&&/\.(heic|heif)$/i.test(blob.name)?'data:image/heic;base64,AA==':create(blob)});
 const heic=Buffer.from('AAAAHGZ0eXBoZWljAAAAAG1pZjFoZWljbWlhZgAAAX1tZXRhAAAAAAAAACFoZGxyAAAAAAAAAABwaWN0AAAAAAAAAAAAAAAAAAAAACJpbG9jAAAAAERAAAEAAQAAAAABoQABAAAAAAAAABcAAAAjaWluZgAAAAAAAQAAABVpbmZlAgAAAAABAABodmMxAAAAAA5waXRtAAAAAAABAAAA/WlwcnAAAADdaXBjbwAAAHZodmNDAQNwAAAAkAAAAAAAHvAA/P34+AAADwNgAAEAGEABDAH//wNwAAADAJAAAAMAAAMAHroCQGEAAQAqQgEBA3AAAAMAkAAAAwAAAwAeoCCBBZbq5Ka5uAhoMCAAAAMDIAAAAwAhYgABAAZEAcFzwIkAAAATY29scm5jbHgAAQANAAaAAAAAFGlzcGUAAAAAAAAAQAAAAEAAAAAoY2xhcAAAACAAAAABAAAAMAAAAAH////gAAAAAv////AAAAACAAAAEHBpeGkAAAAAAwgICAAAABhpcG1hAAAAAAAAAAEAAQWBAgMFhAAAAB9tZGF0AAAAEygBrxOA+FDQp9Q/dMzsZilTV4A=','base64');
 let originalUploaded=false;
 await page.route('**/api/profile/avatar/**',async route=>{if(route.request().method()==='POST')originalUploaded=route.request().postDataBuffer().includes(heic);await route.fallback()});
 await page.goto('/?page=profile');
 await page.locator('.profile-hero input[type=file]').first().setInputFiles({name:'phone.heic',mimeType:'image/heic',buffer:heic});
 const cropper=page.locator('.profile-cropper-sheet');
 await expect(cropper.getByRole('alert')).toContainText('HEIC/HEIF');
 await expect(cropper.locator('input[type=range]')).toBeDisabled();
 const save=cropper.getByRole('button',{name:'Ohne Vorschau speichern',exact:true});
 await expect(save).toBeEnabled();await save.click();
 await expect(cropper).toHaveCount(0);expect(originalUploaded).toBe(true);
 await expect(page.locator('.profile-hero img')).toBeVisible();
});
