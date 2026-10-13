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
 await page.locator('.pin-card summary').click();
 const link=page.getByRole('link',{name:'Quelle zusätzlich freigeben'});
 await expect(link).toBeVisible();
 await expect(link).toHaveAttribute('href',shareUrl);
 await expect(page.locator('.pin-card')).toContainText('Nur mich');
});

for(const [language,label,scope] of [["fr", "Partager aussi la source", "Moi uniquement"], ["nl", "Bron ook delen", "Alleen ik"], ["th", "แชร์ต้นฉบับด้วย", "ฉันเท่านั้น"]]) {
 test(`source sharing uses the selected ${language} language`,async({page})=>{
  await installApiMocks(page,{language,dismissOnboarding:true});
  await page.route("**/api/board/**",route=>route.fulfill({json:{count:1,next:null,results:[{id:"pin-locale",family:"family-1",author:1,kind:"note_ref",target:{available:true,title:"Source",can_share_source:true,source_share_url:"/?page=notes&note=n&share=1"},visibility:"family",effective_scope:"private",images:[],can_change_pin_visibility:false,can_delete:false,can_reorder:false}]}}));
  await page.goto("/?page=board");
  await page.locator(".pin-card summary").click();
  await expect(page.getByRole("link",{name:label,exact:true})).toHaveAttribute("href","/?page=notes&note=n&share=1");
  await expect(page.locator(".pin-card")).toContainText(scope);
 });
}
