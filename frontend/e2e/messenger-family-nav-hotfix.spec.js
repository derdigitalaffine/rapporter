import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const chatId='22222222-2222-4222-8222-222222222222';
const derivedId='33333333-3333-4333-8333-333333333333';
const json=(route,data,status=200)=>route.fulfill({json:data,status});

async function boot(page){
 await installApiMocks(page);
 const requests=[];
 const chat={id:chatId,kind:'direct',title:'Sam',friendship_id:derivedId,state:'active',can_send:true,muted:false,revision:2,last_read_sequence:0,unread:5,last_message:null,participants:[{id:1,display_name:'Alex',state:'active'},{id:2,display_name:'Sam',state:'active'}],typing:[],read_receipts:[]};
 await page.route('**/api/chat/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname,method=req.method();let body={};try{body=req.postDataJSON()||{}}catch{}
  requests.push({path,method,body});
  if(path==='/api/chat/account/')return json(route,{user_id:1,display_name:'Alex',locale:'de',push_enabled:true,read_receipts:true,can_chat:true});
  if(path==='/api/chat/conversations/')return json(route,{results:[chat]});
  if(path==='/api/chat/contacts/')return json(route,{friends:[{id:derivedId,user:{id:2,display_name:'Sam'}}],incoming:[],outgoing:[],blocked:[]});
  if(path==='/api/chat/family-contacts/')return json(route,{results:[{user:{id:2,display_name:'Sam',avatar_url:null},source:'family'}],derived_friendship_ids:[derivedId]});
  if(path==='/api/chat/family-conversations/'&&method==='POST')return json(route,chat,201);
  if(path===`/api/chat/conversations/${chatId}/messages/`)return json(route,{results:[],cursor:2,has_more:false,before:null,conversation:chat});
  if(path===`/api/chat/conversations/${chatId}/`)return json(route,chat);
  if(path.endsWith('/read/')||path.endsWith('/typing/'))return json(route,{ok:true});
  return json(route,{});
 });
 await page.goto('/');
 await expect(page.locator('.bottom-nav')).toBeVisible();
 return {requests};
}

test('Messenger is the canonical header destination with personal unread badge',async({page})=>{
 await boot(page);
 const messenger=page.locator('.header-messenger-button');
 await expect(messenger).toBeVisible();
 await expect(messenger.locator('.header-messenger-badge')).toHaveText('5');
 await messenger.click();
 await expect(page).toHaveURL(/page=inbox/);
 await expect(page.locator('main').getByRole('heading',{name:'Nachrichten',exact:true})).toBeVisible();
 await expect(page.locator('.bottom-nav')).toBeVisible();
 await expect(messenger).toHaveAttribute('aria-current','page');
 await page.locator('.messenger-page-head').getByRole('button',{name:'Zurück',exact:true}).click();
 await expect(messenger).not.toHaveAttribute('aria-current','page');
});

test('own-family member opens direct chat without invitation or acceptance',async({page})=>{
 const state=await boot(page);
 await page.locator('.header-messenger-button').click();
 await page.getByRole('button',{name:/Freunde/}).first().click();
 const familySection=page.locator('.messenger-contacts .card').filter({has:page.getByRole('heading',{name:'Freunde',exact:true})});
 await expect(familySection).toContainText('Familienmitglieder erscheinen hier automatisch');
 await familySection.getByRole('button',{name:/Sam/}).click();
 await expect.poll(()=>state.requests.some(request=>request.path==='/api/chat/family-conversations/'&&request.method==='POST'&&request.body.user_id===2)).toBe(true);
 expect(state.requests.some(request=>request.path==='/api/chat/invitations/'&&request.method==='POST')).toBe(false);
 expect(state.requests.some(request=>request.path==='/api/chat/conversations/'&&request.method==='POST')).toBe(false);
});
