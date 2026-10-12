import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function summary(state){return {comment_count:state.comments.length,has_unread_comments:false,reactions:state.reaction?[{key:state.reaction,count:1,mine:true}]:[],can_interact:true,muted:state.muted}}
function pin(state){return {id:'pin-interaction',family:'family-1',text:'Wer bringt Kuchen mit?',kind:'note',adapter_key:'',target_id:null,target:null,visibility:'family',selected_membership_ids:[],effective_scope:'family',position:0,author:1,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,can_reorder:true,can_change_pin_visibility:true,can_share_source:false,can_interact:true,images:[],interaction:summary(state)}}

async function boot(page,language='de',{multipleFamilies=false}={}){
 const apiState=await installApiMocks(page,{language});
 if(multipleFamilies)await page.route('**/api/families/',route=>route.fulfill({json:[apiState.family,{...apiState.family,id:'family-2',name:'Andere Familie'}]}));
 const state={reaction:null,muted:false,comments:[],requests:[]};
 await page.route('**/api/board/**',async route=>{
  const request=route.request(),method=request.method(),url=new URL(request.url()),path=url.pathname;let body={};try{body=request.postDataJSON()||{}}catch{}
  state.requests.push({method,path,body});
  if(path==='/api/board/'&&method==='GET')return route.fulfill({json:{count:state.revoked||url.searchParams.get('family')==='family-2'?0:1,next:null,results:state.revoked||url.searchParams.get('family')==='family-2'?[]:[pin(state)]}});
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
 await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>document.documentElement.style.zoom='2');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.evaluate(()=>document.documentElement.style.zoom='1');
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

test('comments focus immediately during delayed reads and keep keyboard focus and body lock',async({page})=>{
 await page.setViewportSize({width:320,height:568});await boot(page);let release;const pending=new Promise(resolve=>release=resolve);
 await page.route('**/api/board/pin-interaction/comments/',async route=>{await pending;return route.fulfill({json:{results:[],next:null}})});
 const previous=await page.evaluate(()=>document.body.style.overflow);const trigger=page.locator('#pin-pin-interaction').getByRole('button',{name:/Kommentieren/});await trigger.click();
 const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'}),input=dialog.getByRole('textbox',{name:'Kommentar schreiben',exact:true});await expect(input).toBeFocused();await expect(dialog.getByRole('status')).toBeVisible();expect(await page.evaluate(()=>document.body.style.overflow)).toBe('hidden');
 release();await expect(dialog.getByRole('status')).toHaveCount(0);await input.fill('Entwurf');const send=dialog.getByRole('button',{name:'Senden',exact:true}),mute=dialog.getByRole('button',{name:'Thread stummschalten'});await send.focus();await page.keyboard.press('Tab');await expect(mute).toBeFocused();await page.keyboard.press('Shift+Tab');await expect(send).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();expect(await page.evaluate(()=>document.body.style.overflow)).toBe(previous);
});

test('ambiguous comment failure preserves the draft and retries with the same client id exactly once',async({page})=>{
 const state=await boot(page);const bodies=[];let saved=null;
 await page.route('**/api/board/pin-interaction/comments/',route=>{
  if(route.request().method()==='GET')return route.fulfill({json:{results:saved?[saved]:[],next:null}});
  const body=route.request().postDataJSON();bodies.push(body);
  if(!saved){saved={id:'retry-comment',body:body.body,author_name:'Alex',created_at:new Date().toISOString(),mine:true,can_edit:true,can_delete:true,reactions:[],interaction:{comment_count:1,reactions:[],can_interact:true}};state.comments.push(saved);return route.fulfill({status:503,json:{detail:'Temporary response failure'}})}
  return route.fulfill({status:201,json:saved});
 });
 await page.locator('#pin-pin-interaction').getByRole('button',{name:/Kommentieren/}).click();const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'}),input=dialog.getByRole('textbox',{name:'Kommentar schreiben',exact:true});await input.fill('Nur einmal speichern');await dialog.getByRole('button',{name:'Senden',exact:true}).click();await expect(dialog.getByRole('alert')).toBeVisible();await expect(input).toHaveValue('Nur einmal speichern');await expect(input).toBeEnabled();await page.evaluate(()=>window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:true}})));await expect(input).toHaveValue('Nur einmal speichern');
 await dialog.getByRole('button',{name:'Senden',exact:true}).click();await expect(dialog.getByText('Nur einmal speichern',{exact:true})).toBeVisible();await expect(input).toHaveValue('');expect(bodies).toHaveLength(2);expect(bodies[0].client_id).toBe(bodies[1].client_id);expect(bodies[0].client_id).toMatch(/^[0-9a-f-]{36}$/);expect(state.comments).toHaveLength(1);
});

test('read failures retry, while a denied older-page read removes known content and the private draft',async({page})=>{
 const state=await boot(page);let initialFailure=true;
 await page.route('**/api/board/pin-interaction/comments/**',route=>{
  const url=new URL(route.request().url());if(url.searchParams.has('cursor')){state.revoked=true;return route.fulfill({status:403,json:{detail:'denied'}})}
  if(initialFailure)return route.fulfill({status:503,json:{detail:'unavailable'}});
  return route.fulfill({json:{next:'/api/board/pin-interaction/comments/?cursor=older',results:[{id:'protected',body:'Berechtigter Inhalt',author_name:'Sam',created_at:new Date().toISOString(),reactions:[]}]}});
 });
 await page.locator('#pin-pin-interaction').getByRole('button',{name:/Kommentieren/}).click();const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'});await expect(dialog.getByRole('alert')).toBeVisible();initialFailure=false;await dialog.getByRole('button',{name:'Erneut versuchen'}).click();await expect(dialog.getByText('Berechtigter Inhalt')).toBeVisible();await dialog.getByRole('textbox',{name:'Kommentar schreiben',exact:true}).fill('Privater Entwurf');await dialog.getByRole('button',{name:'Ältere Kommentare laden'}).click();await expect(dialog).toHaveCount(0);await expect(page.getByText('Berechtigter Inhalt')).toHaveCount(0);await expect(page.getByText('Wer bringt Kuchen mit?',{exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:/Kommentieren/})).toHaveCount(0);
});

test('late mutation success cannot restore interaction metadata after auth invalidation',async({page})=>{
 await boot(page);let release;const pending=new Promise(resolve=>release=resolve);let requested=false;
 await page.route('**/api/board/pin-interaction/reaction/',async route=>{requested=true;await pending;return route.fulfill({json:{comment_count:9,can_interact:true,reactions:[{key:'thumbs_up',count:1,mine:true}]}})});
 const card=page.locator('#pin-pin-interaction');await card.getByRole('button',{name:'Reagieren',exact:true}).click();await page.getByRole('button',{name:'Passt',exact:true}).click();await expect.poll(()=>requested).toBe(true);
 await page.evaluate(()=>{localStorage.removeItem('famuhle-session');window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:false}}))});await expect(card).toHaveCount(0);release();await expect(page.getByRole('button',{name:'Passt, 1'})).toHaveCount(0);await expect(page.getByRole('button',{name:/Kommentieren, 9/})).toHaveCount(0);
});

for(const [language,react,dialogName,write] of [['fr','Réagir','Commentaires du pin','Écrire un commentaire'],['nl','Reageren','Pinopmerkingen','Schrijf een opmerking'],['th','แสดงความรู้สึก','ความคิดเห็นบนหมุด','เขียนความคิดเห็น']])test(`pin interaction copy supports ${language} without German fallback`,async({page})=>{
 await boot(page,language);const card=page.locator('#pin-pin-interaction');await expect(card.getByRole('button',{name:react,exact:true})).toBeVisible();await card.locator('.pin-comment-action').click();const dialog=page.getByRole('dialog',{name:dialogName});await expect(dialog).toBeVisible();await expect(dialog.getByRole('textbox',{name:write,exact:true})).toBeFocused();
});

test('older comment pages stay chronological and do not repeat overlapping comment ids',async({page})=>{
 await boot(page);const make=(id,body)=>({id,body,author_name:'Sam',created_at:new Date().toISOString(),reactions:[]});
 await page.route('**/api/board/pin-interaction/comments/**',route=>new URL(route.request().url()).searchParams.has('cursor')?route.fulfill({json:{next:null,results:[make('newer','Neuer Kommentar'),make('older','Alter Kommentar')]}}):route.fulfill({json:{next:'/api/board/pin-interaction/comments/?cursor=older',results:[make('newer','Neuer Kommentar')]}}));
 await page.locator('#pin-pin-interaction').getByRole('button',{name:/Kommentieren/}).click();const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'});await dialog.getByRole('button',{name:'Ältere Kommentare laden'}).click();await expect(dialog.locator('.pin-comment-body')).toHaveText(['Alter Kommentar','Neuer Kommentar']);await expect(dialog.getByRole('button',{name:'Ältere Kommentare laden'})).toHaveCount(0);
});

test('reaction picker sends one desired-state operation while pending',async({page})=>{
 await boot(page);let release;const pending=new Promise(resolve=>release=resolve),requests=[];
 await page.route('**/api/board/pin-interaction/reaction/',async route=>{requests.push(route.request().postDataJSON());await pending;return route.fulfill({json:{comment_count:0,can_interact:true,reactions:[{key:'thumbs_up',count:1,mine:true}]}})});
 const card=page.locator('#pin-pin-interaction');await card.getByRole('button',{name:'Reagieren',exact:true}).click();await page.getByRole('button',{name:'Passt',exact:true}).click();await expect(page.getByRole('button',{name:'Herz',exact:true})).toBeDisabled();expect(requests).toEqual([{key:'thumbs_up'}]);release();await expect(card.getByRole('button',{name:'Passt, 1'})).toHaveAttribute('aria-pressed','true');
});

test('a late initial history read does not erase the comment confirmed while it was pending',async({page})=>{
 await boot(page);let release;const pending=new Promise(resolve=>release=resolve);let created=false;
 await page.route('**/api/board/pin-interaction/comments/',async route=>{if(route.request().method()==='GET'){await pending;return route.fulfill({json:{results:[],next:null}})}created=true;const body=route.request().postDataJSON();return route.fulfill({status:201,json:{id:'confirmed-during-read',body:body.body,author_name:'Alex',created_at:new Date().toISOString(),reactions:[],interaction:{comment_count:1,has_unread_comments:false,can_interact:true,reactions:[]}}})});
 const card=page.locator('#pin-pin-interaction');await card.getByRole('button',{name:/Kommentieren/}).click();const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'}),input=dialog.getByRole('textbox',{name:'Kommentar schreiben',exact:true});await expect(input).toBeFocused();await input.fill('Bestätigt während Ladevorgang');await dialog.getByRole('button',{name:'Senden',exact:true}).click();await expect.poll(()=>created).toBe(true);await expect(input).toHaveValue('');release();await expect(dialog.getByText('Bestätigt während Ladevorgang',{exact:true})).toBeVisible();await expect(dialog.locator('.pin-thread-head')).toContainText('1 Kommentare');await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(card.getByRole('button',{name:/Kommentieren, 1 Kommentare/})).toBeVisible();
});

test('changing family unmounts the old thread and ignores its delayed mutation success',async({page})=>{
 await boot(page,'de',{multipleFamilies:true});let release;const pending=new Promise(resolve=>release=resolve);let requested=false;
 await page.route('**/api/board/pin-interaction/reaction/',async route=>{requested=true;await pending;return route.fulfill({json:{comment_count:9,can_interact:true,reactions:[{key:'thumbs_up',count:1,mine:true}]}})});
 const card=page.locator('#pin-pin-interaction');await card.getByRole('button',{name:'Reagieren',exact:true}).click();await page.getByRole('button',{name:'Passt',exact:true}).click();await expect.poll(()=>requested).toBe(true);await page.locator('.family-switcher select').selectOption('family-2');await expect(card).toHaveCount(0);release();await expect(page.locator('.family-switcher select')).toHaveValue('family-2');await page.locator('.bottom-nav button').filter({hasText:'Mehr'}).click();await page.getByRole('button',{name:'Pinnwand',exact:true}).click();await expect(page.getByRole('heading',{name:'Pinnwand',exact:true})).toBeVisible();await expect(card).toHaveCount(0);await expect(page.getByRole('button',{name:/Kommentieren, 9/})).toHaveCount(0);
});

test('comment moderation delegates to the visible shared confirmation and cancel keeps the thread',async({page})=>{
 const state=await boot(page);await page.locator('#pin-pin-interaction').getByRole('button',{name:/Kommentieren/}).click();const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'});await dialog.getByRole('textbox',{name:'Kommentar schreiben',exact:true}).fill('Kommentar behalten');await dialog.getByRole('button',{name:'Senden',exact:true}).click();const comment=dialog.locator('.pin-comment').filter({hasText:'Kommentar behalten'});await comment.getByRole('button',{name:'Entfernen',exact:true}).click();const confirmation=page.getByRole('alertdialog');await expect(confirmation).toBeVisible();const cancel=confirmation.getByRole('button',{name:'Abbrechen',exact:true});await expect(cancel).toBeFocused();await page.keyboard.press('Tab');await expect(confirmation.getByRole('button',{name:'Entfernen',exact:true})).toBeFocused();await page.keyboard.press('Shift+Tab');await expect(cancel).toBeFocused();await cancel.click();await expect(confirmation).toHaveCount(0);await expect(dialog).toBeVisible();await expect(comment).toBeVisible();expect(state.requests.filter(row=>row.method==='DELETE')).toHaveLength(0);
});
