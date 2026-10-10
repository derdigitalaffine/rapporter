import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const UPDATED_AT='2026-10-10T22:00:00.000Z';

function trip(extra={}){
 return {
  id:'trip-1',family:'family-1',title:'Japan',destination:'Tokyo',stage:'planning',
  date_precision:'season',date_year:2028,date_month:null,date_season:'autumn',starts_on:null,ends_on:null,
  notes:'',archived:false,created_by:1,creator_name:'Alex',calendar_event_id:null,photos:[],
  can_manage:true,can_add_photos:true,created_at:'2026-10-10T20:00:00.000Z',updated_at:UPDATED_AT,
  ...extra,
 };
}

async function installTravelApi(page,{rows=[trip()],onPatch,onPost}={}){
 await installApiMocks(page,{dismissOnboarding:true});
 await page.route('**/api/trips/**',async route=>{
  const request=route.request();const url=new URL(request.url());const method=request.method();
  if(url.pathname==='/api/trips/'&&method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(rows)});
  if(url.pathname==='/api/trips/'&&method==='POST'){
   const body=request.postDataJSON();if(onPost)onPost(body);
   const created=trip({id:'trip-created',...body,date_year:body.date_year??null,date_month:body.date_month??null,date_season:body.date_season??'',starts_on:body.starts_on??null,ends_on:body.ends_on??null,updated_at:'2026-10-10T22:01:00.000Z'});
   rows.push(created);return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify(created)});
  }
  if(/^\/api\/trips\/[^/]+\/$/.test(url.pathname)&&method==='PATCH'){
   const body=request.postDataJSON();if(onPatch)onPatch(body);
   const index=rows.findIndex(row=>url.pathname===`/api/trips/${row.id}/`);const current=rows[index];
   const updated={...current,...body,updated_at:'2026-10-10T22:02:00.000Z'};delete updated.expected_updated_at;rows[index]=updated;
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(updated)});
  }
  return route.fallback();
 });
 return rows;
}

test('Travel v2 shows approximate dates and sends the optimistic edit token',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 let patchBody=null;await installTravelApi(page,{onPatch:body=>{patchBody=body}});
 await page.goto('/?page=trips');
 await expect(page.getByRole('heading',{name:'Reisen',exact:true})).toBeVisible();
 await expect(page.getByText('Herbst 2028')).toBeVisible();
 await expect(page.getByText('Planung',{exact:true}).first()).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflow).toBeLessThanOrEqual(0);

 await page.getByRole('button',{name:'Reise bearbeiten'}).click();
 await expect(page.getByLabel('Wie genau?')).toHaveValue('season');
 await page.getByLabel('Reisename').fill('Japan gemeinsam');
 await page.getByRole('button',{name:'Speichern'}).click();
 await expect.poll(()=>patchBody).not.toBeNull();
 expect(patchBody.expected_updated_at).toBe(UPDATED_AT);
 expect(patchBody.date_precision).toBe('season');
 expect(patchBody.date_year).toBe(2028);
 expect(patchBody.date_season).toBe('autumn');
 expect(patchBody.starts_on).toBeUndefined();
 expect(patchBody.ends_on).toBeUndefined();
 await expect(page.getByRole('heading',{name:'Japan gemeinsam'})).toBeVisible();
});

test('a vague trip can be created without fake exact dates',async({page})=>{
 let postBody=null;await installTravelApi(page,{rows:[],onPost:body=>{postBody=body}});
 await page.goto('/?page=trips');
 await page.getByRole('button',{name:'Reise planen'}).first().click();
 await page.getByLabel('Reisename').fill('Irgendwann Island');
 await expect(page.getByLabel('Wie genau?')).toHaveValue('unknown');
 await expect(page.locator('input[type="date"]')).toHaveCount(0);
 await page.getByRole('button',{name:'Speichern'}).click();
 await expect.poll(()=>postBody).not.toBeNull();
 expect(postBody.date_precision).toBe('unknown');
 expect(postBody.stage).toBe('idea');
 expect(postBody.starts_on).toBeUndefined();
 expect(postBody.ends_on).toBeUndefined();
 await expect(page.getByText('Zeitraum offen')).toBeVisible();
});
