import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function summary(state){return {comment_count:state.comments.length,has_unread_comments:false,reactions:state.reaction?[{key:state.reaction,count:1,mine:true}]:[],can_interact:true,muted:state.muted}}
function pin(state){return {id:'pin-interaction',family:'family-1',text:'Wer bringt Kuchen mit?',kind:'note',adapter_key:'',target_id:null,target:null,visibility:'family',selected_membership_ids:[],effective_scope:'family',position:0,author:1,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,can_reorder:true,can_change_pin_visibility:true,can_share_source:false,can_interact:true,images:[],interaction:summary(state)}}

async function boot(page,language='de'){
 await installApiMocks(page,{language});
 const state={reaction:null,muted:false,comments:[],requests:[]};
 await page.route('**/api/board/**',async route=>{
  const request=route.request(),method=request.method(),url=new URL(request.url()),path=url.pathname;let body={};try{body=request.postDataJSON()||{}}catch{}
  state.requests.push({method,path,body});
  if(path==='/api/board/'&&method==='GET')return route.fulfill({json:{count:1,next:null,results:[pin(state)]}});
  if(path==='/api/board/pin-interaction/reaction/'&&method==='PUT'){state.reaction=body.key||null;return route.fulfill({json:summary(state)})}
  if(path==='/api/board/pin-interaction/mention-targets/'&&method==='GET')return route.fulfill({json:[{id:'member-2',name:'Sam'}]});
  if(path==='/api/board/pin-interaction/comments/'&&method==='GET')return route.fulfill({json:{next:null,previous:null,results:[...state.comments].reverse()}});
  if(path==='/api/board/pin-interaction/comments/'&&method==='POST'){
   const row={id:`comment-${state.comments.length+1}`,body:body.body,deleted:false,author_id:1,author_name:'Alex',created_at:new Date().toISOString(),updated_at:new Date().toISOString(),edited:false,mine:true,can_edit:true,can_delete:true,mentions:(body.mention_membership_ids||[]).map(id=>({id,name:'Sam'})),reactions:[],interaction:null};state.comments.push(row);row.interaction=summary(state);return route.fulfill({status:201,json:row});
  }
  if(path==='/api/board/pin-interaction/mute/'&&method==='POST'){state.muted=Boolean(body.muted);return route.fulfill({json:summary(state)})}
  if(path.match(/^\/api\/board\/pin-interaction\/comments\/comment-\d+\/reaction\/$/)&&method==='PUT'){
   const id=path.split('/')[5],row=state.comments.find(item=>item.id===id);row.reactions=body.key?[{key:body.key,count:1,mine:true}]:[];return route.fulfill({json:row})
  }
  return route.fulfill({status:404,json:{detail:'not found'}});
 });
 await page.goto('/?page=board');
 return state;
}

test('pin reactions toggle with one tap and comment sheet is mobile/keyboard safe',async({page})=>{
 await page.setViewportSize({width:390,height:844});const state=await boot(page);
 const card=page.locator('#pin-pin-interaction');await expect(card).toBeVisible();
 const react=card.getByRole('button',{name:'Reagieren',exact:true});const reactBox=await react.boundingBox();expect(reactBox.height).toBeGreaterThanOrEqual(44);
 await react.click();await page.getByRole('button',{name:'Passt',exact:true}).click();
 const chip=card.getByRole('button',{name:'Passt, 1'});await expect(chip).toHaveAttribute('aria-pressed','true');expect(state.reaction).toBe('thumbs_up');
 await chip.click();await expect(chip).toHaveCount(0);expect(state.reaction).toBeNull();

 const commentButton=card.getByRole('button',{name:/Kommentieren/});await commentButton.click();
 const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'});await expect(dialog).toBeVisible();
 const input=dialog.locator('textarea').last();await expect(input).toBeFocused();await input.fill('Komme später.');await dialog.getByRole('button',{name:'Senden',exact:true}).click();
 await expect(dialog.getByText('Komme später.',{exact:true})).toBeVisible();
 const comment=dialog.locator('.pin-comment').filter({hasText:'Komme später.'});await comment.getByRole('button',{name:'Reagieren',exact:true}).click();await comment.getByRole('button',{name:'Passt',exact:true}).click();await expect(comment.getByRole('button',{name:'Passt, 1'})).toHaveAttribute('aria-pressed','true');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(commentButton).toBeFocused();
 await expect(card.getByRole('button',{name:/Kommentieren, 1 Kommentare/})).toBeVisible();
});

test('mention picker sends only the selected membership id and thread can be muted',async({page})=>{
 const state=await boot(page);const card=page.locator('#pin-pin-interaction');await card.getByRole('button',{name:/Kommentieren/}).click();const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'});const input=dialog.locator('textarea').last();
 await input.fill('@Sa');await dialog.getByRole('option',{name:'@Sam'}).click();await input.fill((await input.inputValue())+' bitte prüfen');await dialog.getByRole('button',{name:'Senden',exact:true}).click();
 const create=state.requests.find(row=>row.method==='POST'&&row.path==='/api/board/pin-interaction/comments/');expect(create.body.mention_membership_ids).toEqual(['member-2']);
 await dialog.getByRole('button',{name:'Thread stummschalten'}).click();expect(state.muted).toBeTruthy();await expect(dialog.getByRole('button',{name:'Stummschaltung aufheben'})).toBeVisible();
});

test('English interaction controls have localized accessible names',async({page})=>{
 await boot(page,'en');const card=page.locator('#pin-pin-interaction');await expect(card.getByRole('button',{name:'React',exact:true})).toBeVisible();await card.getByRole('button',{name:/Comment/}).click();const dialog=page.getByRole('dialog',{name:'Pin comments'});await expect(dialog).toBeVisible();await expect(dialog.getByRole('button',{name:'Close comments'})).toBeVisible();
});
