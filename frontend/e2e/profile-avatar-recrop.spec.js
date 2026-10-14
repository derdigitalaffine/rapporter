import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');

test('existing profile photo can be reopened, zoomed and saved with a new crop',async({page})=>{
 await installApiMocks(page);
 let uploaded=false;
 let profile={user_id:1,username:'alex',email:'alex@example.test',avatar_url:'/api/profile/avatar/1/256/?v=existing',birth_month:3,birth_day:12,birth_year:null,family:'family-1',membership_id:'member-1',display_name:'Alex',role:'owner',birthday_visibility:'day_month',show_birthday_age:true,calendar_color:'#4f7cff',calendar_color_palette:['#4f7cff','#eb6f92','#3aa981']};
 await page.route('**/api/profile/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname;const method=request.method();
  if(path==='/api/profile/avatar/1/256/'&&method==='GET')return route.fulfill({status:200,contentType:'image/png',body:png});
  if(path==='/api/profile/avatar/'&&method==='POST'){uploaded=true;profile={...profile,avatar_url:'/api/profile/avatar/1/256/?v=recropped'};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(profile)})}
  if(path==='/api/profile/'&&method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(profile)});
  return route.fallback();
 });
 await page.goto('/?page=profile');
 await expect(page.locator('.profile-hero img')).toBeVisible();
 await page.getByRole('button',{name:'Ausschnitt bearbeiten',exact:true}).click();
 const cropper=page.locator('.profile-cropper-sheet');
 await expect(cropper.getByRole('heading',{name:'Bildausschnitt einstellen'})).toBeVisible();
 const zoom=cropper.locator('input[type=range]');
 await expect(zoom).toBeEnabled();
 await zoom.fill('2.25');
 await cropper.getByRole('button',{name:'Ausschnitt verwenden',exact:true}).click();
 await expect(cropper).toHaveCount(0);
 expect(uploaded).toBe(true);
 await expect(page.getByText('Profilfoto aktualisiert.')).toBeVisible();
 await expect(page.locator('.profile-hero img')).toBeVisible();
});