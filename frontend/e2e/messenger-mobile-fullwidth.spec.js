import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const chatId='22222222-2222-4222-8222-222222222222';
const json=(route,data,status=200)=>route.fulfill({json:data,status});

test('selected mobile chat fills the viewport width',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await installApiMocks(page);
 const chat={id:chatId,kind:'direct',title:'Bastian',state:'active',can_send:true,muted:false,revision:2,last_read_sequence:0,unread:0,last_message:{id:'m1',body:'Hallo',created_at:new Date().toISOString(),deleted:false},participants:[{id:1,display_name:'Alex',state:'active'},{id:2,display_name:'Bastian',state:'active'}],typing:[],read_receipts:[]};
 await page.route('**/api/chat/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/chat/account/')return json(route,{user_id:1,display_name:'Alex',locale:'de',push_enabled:true,read_receipts:true,can_chat:true});
  if(path==='/api/chat/conversations/')return json(route,{results:[chat]});
  if(path==='/api/chat/contacts/')return json(route,{friends:[],incoming:[],outgoing:[],blocked:[]});
  if(path==='/api/chat/family-contacts/')return json(route,{results:[],derived_friendship_ids:[]});
  if(path===`/api/chat/conversations/${chatId}/messages/`)return json(route,{results:[],cursor:0,has_more:false,before:null,conversation:chat});
  if(path===`/api/chat/conversations/${chatId}/`)return json(route,chat);
  if(path.endsWith('/read/')||path.endsWith('/typing/'))return json(route,{ok:true});
  return json(route,{});
 });
 await page.goto(`/?page=inbox&chat=${chatId}`);
 const messenger=page.locator('.messenger-page.has-selection');
 const layout=messenger.locator('.messenger-layout');
 const thread=messenger.locator('.messenger-thread');
 await expect(thread).toBeVisible();
 await expect.poll(async()=>page.evaluate(()=>{
  const viewport=window.innerWidth;
  const box=document.querySelector('.messenger-thread')?.getBoundingClientRect();
  return box?Math.abs(box.width-viewport):999;
 })).toBeLessThanOrEqual(2);
 await expect.poll(async()=>layout.evaluate(el=>getComputedStyle(el).display)).toBe('block');
 await expect.poll(async()=>page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);
});
