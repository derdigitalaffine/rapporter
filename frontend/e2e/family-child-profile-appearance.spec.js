import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
const palette=['#4f7cff','#eb6f92','#3aa981'];
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

test('adult can manage child photo and avatar color even without child-account guardian access',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const state=await installApiMocks(page);state.memberships[0].role='adult';
 const memberships=[
  {id:'member-1',family:'family-1',user:1,username:'alex',role:'adult',display_name:'Alex',avatar:'',avatar_url:'',calendar_color:palette[0],calendar_color_palette:palette},
  {id:'member-child-1',family:'family-1',user:3,username:'child-managed',role:'child',display_name:'Mia',avatar:'',avatar_url:'',calendar_color:palette[0],calendar_color_palette:palette},
 ];
 let memberPatch=null;let avatarUploads=0;
 await page.route('**/api/memberships/',route=>json(route,memberships));
 await page.route('**/api/memberships/member-child-1/',route=>{memberPatch=route.request().postDataJSON();Object.assign(memberships[1],memberPatch);return json(route,memberships[1])});
 await page.route('**/api/invitations/',route=>json(route,[]));
 await page.route('**/api/family-settings/**',route=>json(route,{family:'family-1',name:'Musterfamilie',slug:'musterfamilie',can_edit:false,image_url:'',address_street:'',address_house_number:'',address_postal_code:'',address_city:'',address_region:'',address_country_code:'',location_context:null}));
 await page.route('**/api/baby/memberships/member-child-1/identity/',route=>json(route,{detail:'guardian required'},403));
 await page.route('**/api/baby/memberships/member-child-1/avatar/',route=>{
  if(route.request().method()==='DELETE'){memberships[1].avatar_url='';memberships[1].avatar='';return json(route,{...memberships[1],avatar_url:''})}
  avatarUploads+=1;memberships[1].avatar_url='/api/profile/avatar/3/128/?v=test';memberships[1].avatar=memberships[1].avatar_url;return json(route,{...memberships[1]});
 });
 await page.route('**/api/profile/avatar/3/128/**',route=>route.fulfill({status:200,contentType:'image/png',body:png}));

 await page.goto('/?page=members');
 await page.getByRole('button',{name:/Mia.*Kind/}).click();
 const sheet=page.locator('.member-sheet');
 await expect(sheet.getByText('Foto & Avatarfarbe')).toBeVisible();
 await expect(sheet.getByText('Eigener Zugang')).toHaveCount(0);

 await sheet.locator('.child-profile-appearance input[type=file]').setInputFiles({name:'mia.png',mimeType:'image/png',buffer:png});
 await expect(page.getByText('Profilbild des Kindes aktualisiert.')).toBeVisible();
 expect(avatarUploads).toBe(1);
 await expect(sheet.locator('.child-profile-preview img')).toBeVisible();

 await sheet.getByRole('button',{name:'Avatarfarbe 2'}).click();
 await sheet.locator('form > .primary').click();
 await expect(page.getByText('Mitglied gespeichert.')).toBeVisible();
 expect(memberPatch.calendar_color).toBe(palette[1]);
 expect(memberPatch.role).toBe('child');
});