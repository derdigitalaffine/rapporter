import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const UPDATED_AT='2026-10-11T00:00:00.000Z';

function trip(extra={}){
 return {
  id:'trip-1',family:'family-1',participants:['member-1'],title:'Familienreise',destination:'Berlin',stage:'planning',
  date_precision:'unknown',date_year:null,date_month:null,date_season:'',starts_on:null,ends_on:null,notes:'',archived:false,
  created_by:1,creator_name:'Alex',calendar_event_id:null,photos:[],can_manage:true,can_add_photos:true,
  created_at:'2026-10-10T20:00:00.000Z',updated_at:UPDATED_AT,...extra,
 };
}

async function installTravelApi(page,onPatch){
 await installApiMocks(page,{dismissOnboarding:true});
 const rows=[trip()];
 await page.route('**/api/trips/**',async route=>{
  const request=route.request();const url=new URL(request.url());const method=request.method();
  if(url.pathname==='/api/trips/'&&method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(rows)});
  if(/^\/api\/trips\/[^/]+\/$/.test(url.pathname)&&method==='PATCH'){
   const body=request.postDataJSON();onPatch(body);
   rows[0]={...rows[0],...body,updated_at:'2026-10-11T00:01:00.000Z'};delete rows[0].expected_updated_at;
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(rows[0])});
  }
  return route.fallback();
 });
}

test('Travel participant picker edits canonical family memberships and stays mobile safe',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 let patchBody=null;await installTravelApi(page,body=>{patchBody=body});
 await page.goto('/?page=trips');

 await page.getByRole('button',{name:'Reise bearbeiten'}).click();
 const editor=page.locator('.travel-editor');
 await editor.getByText('Weitere Planungsdetails').click();
 await expect(editor.getByLabel('Alex')).toBeChecked();
 await expect(editor.getByLabel('Sam')).not.toBeChecked();
 await editor.getByLabel('Alex').uncheck();
 await editor.getByLabel('Sam').check();
 await editor.getByRole('button',{name:'Speichern'}).click();

 await expect.poll(()=>patchBody).not.toBeNull();
 expect(patchBody.participants).toEqual(['member-2']);
 expect(patchBody.expected_updated_at).toBe(UPDATED_AT);

 await page.getByRole('button',{name:'Öffnen'}).click();
 const participants=page.locator('.travel-participants');
 await expect(participants.getByRole('heading',{name:'Reisende'})).toBeVisible();
 await expect(participants.getByText('Sam',{exact:true})).toBeVisible();
 await expect(participants.getByText('Alex',{exact:true})).toHaveCount(0);
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflow).toBeLessThanOrEqual(0);
});
