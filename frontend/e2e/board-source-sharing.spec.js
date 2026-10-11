import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';


test('note source sharing is a separate canonical action',async({page})=>{
 await installApiMocks(page,{language:'de'});
 const shareUrl='/?page=notes&note=note-share-1&share=1';
 await page.route('**/api/board/**',async route=>{
  if(route.request().method()!=='GET')return route.fulfill({status:405,json:{detail:'method_not_allowed'}});
  return route.fulfill({json:{count:1,next:null,results:[{
   id:'pin-share-1',family:'family-1',author:1,author_name:'Alex',text:'',kind:'note_ref',adapter_key:'note',target_id:'note-share-1',
   target:{id:'note-share-1',kind:'note_ref',title:'Private Notiz',subtitle:'',url:'/?page=notes&note=note-share-1',can_share_source:true,source_share_url:shareUrl},
   visibility:'private',selected_membership_ids:[],effective_scope:'private',can_change_pin_visibility:true,can_share_source:true,can_interact:true,
   position:0,created_at:'2026-10-12T08:00:00Z',updated_at:'2026-10-12T08:00:00Z',images:[],can_edit:true,can_delete:true,can_reorder:true,
  }]}});
 });
 await page.goto('/?page=board');
 const link=page.getByRole('link',{name:'Quelle zusätzlich freigeben'});
 await expect(link).toBeVisible();
 await expect(link).toHaveAttribute('href',shareUrl);
 await expect(page.locator('.pin-card')).toContainText('Nur mich');
});
