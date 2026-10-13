import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';
const friendId='11111111-1111-4111-8111-111111111111',chatId='22222222-2222-4222-8222-222222222222';
const json=(route,data,status=200)=>route.fulfill({json:data,status});
async function boot(page,{language='de',familyless=false,failSend=false}={}){
 await installApiMocks(page,{language});
 if(familyless)await page.route('**/api/families/',route=>json(route,[]));
 const account={user_id:1,display_name:'Alex',locale:language,push_enabled:true,read_receipts:true,can_chat:true};
 const chat={id:chatId,kind:'direct',title:'Kim',friendship_id:friendId,state:'active',can_send:true,muted:false,revision:1,last_read_sequence:0,unread:1,last_message:null,participants:[{id:1,display_name:'Alex',state:'active'},{id:9,display_name:'Kim',state:'active'}],typing:[],read_receipts:[]};
 const rows=[{id:'message-1',sender_id:9,sender_name:'Kim',client_id:'initial',sequence:1,event_sequence:1,body:'Hallo aus der anderen Familie',created_at:new Date().toISOString(),edited:false,deleted:false,reply:null,attachments:[],reactions:[]}];
 chat.last_message=rows[0];
 const contacts={friends:[{id:friendId,user:{id:9,display_name:'Kim'}}],incoming:[{id:'invite-1',sender:{id:7,display_name:'Jo'},expires_at:new Date().toISOString()}],outgoing:[],blocked:[]};
 const state={chat,rows,contacts,requests:[],failSend};
 await page.route('**/api/chat/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname,method=req.method();let body={};try{body=req.postDataJSON()||{}}catch{}
  state.requests.push({path,method,body});
  if(path==='/api/chat/account/'){if(method==='PATCH')Object.assign(account,body);return json(route,account)}
  if(path==='/api/chat/contacts/')return json(route,contacts);
  if(path==='/api/chat/invitations/'){contacts.outgoing.push({id:'outgoing',email:body.email,status:'pending'});return json(route,{id:'outgoing'},202)}
  if(path==='/api/chat/invitations/invite-1/'){contacts.incoming=[];return json(route,{friendship_id:friendId})}
  if(path===`/api/chat/contacts/${friendId}/`){chat.can_send=false;contacts.friends=[];return json(route,{ok:true})}
  if(path==='/api/chat/conversations/')return method==='POST'?json(route,chat,201):json(route,{results:[chat]});
  if(path===`/api/chat/conversations/${chatId}/messages/`){
   if(method==='POST'){
    if(state.failSend)return json(route,{detail:'temporary'},503);
    const raw=req.postData()||'';const text=raw.match(/name="body"\r\n\r\n([\s\S]*?)\r\n--/)?.[1]||'';const key=raw.match(/name="client_id"\r\n\r\n([^\r]+)/)?.[1]||'';
    const msg={...rows[0],id:'message-'+(rows.length+1),sender_id:1,sender_name:'Alex',body:text,client_id:key,sequence:++chat.revision,event_sequence:chat.revision};rows.push(msg);chat.last_message=msg;return json(route,msg,201)
   }
   const q=url.searchParams.get('q');return json(route,{results:rows.filter(row=>!q||row.body.includes(q)),cursor:chat.revision,has_more:false,before:1,conversation:chat})
  }
  if(path===`/api/chat/conversations/${chatId}/`){if(method==='PATCH')Object.assign(chat,body);return json(route,chat)}
  if(path.includes('/messages/')&&method==='DELETE'){rows[0].body='';rows[0].deleted=true;rows[0].event_sequence=++chat.revision;return json(route,rows[0])}
  if(path.endsWith('/typing/')||path.endsWith('/read/'))return json(route,{ok:true});
  return json(route,{},404);
 });
 await page.route('**/api/games/**',route=>json(route,[]));
 await page.goto('/?page=inbox');await expect(page.getByRole('heading',{name:language==='en'?'Messages':'Nachrichten',exact:true})).toBeVisible();
 return state;
}
async function openChat(page){await page.locator('.messenger-chat-row').click();await expect(page.locator('.messenger-bubble')).toContainText('Hallo aus der anderen Familie')}

test('personal chat sends canonical retry-safe message and leaves family notices reachable',async({page})=>{
 const state=await boot(page);await openChat(page);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Hallo Kim');await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.locator('.messenger-bubble.own')).toContainText('Hallo Kim');await expect(page.getByRole('textbox',{name:'Nachricht',exact:true})).toHaveValue('');expect(state.requests.some(r=>r.path==='/api/inbox/'&&r.method==='POST')).toBe(false);if(await page.locator('.messenger-mobile-back').isVisible())await page.locator('.messenger-mobile-back').click();await page.getByRole('button',{name:'Familien-Mitteilungen',exact:true}).click();await expect(page.getByRole('heading',{name:'Mitteilungen',exact:true})).toBeVisible();
});

test('send failure retains draft and stable retry UUID',async({page})=>{
 const state=await boot(page,{failSend:true});await openChat(page);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Retry me');await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.getByRole('alert')).toContainText('fehlgeschlagen');await expect(page.getByRole('textbox',{name:'Nachricht',exact:true})).toHaveValue('Retry me');state.failSend=false;await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.locator('.messenger-bubble.own')).toContainText('Retry me');expect(state.rows.at(-1).client_id).toMatch(/^[0-9a-f-]{36}$/);
});

test('email contact invitation and acceptance use explicit personal endpoints',async({page})=>{
 const state=await boot(page);await page.getByRole('button',{name:/Freunde/}).first().click();await page.getByRole('textbox',{name:'E-Mail-Adresse',exact:true}).fill('outside@example.com');await page.getByRole('button',{name:'Einladung senden',exact:true}).click();await expect(page.getByRole('status')).toContainText('Einladung gesendet');expect(state.requests.find(r=>r.path==='/api/chat/invitations/'&&r.method==='POST').body).toMatchObject({email:'outside@example.com'});await page.getByRole('button',{name:'Annehmen',exact:true}).click();await expect(page.getByRole('heading',{name:'Kontaktanfragen'})).toHaveCount(0);expect(state.requests.some(r=>r.path.includes('/families/')&&r.method==='POST')).toBe(false);
});

test('typing and read receipts render only inside chosen chat',async({page})=>{
 const state=await boot(page);state.chat.typing=[{id:9,display_name:'Kim'}];await openChat(page);await expect(page.locator('.messenger-chat-title')).toContainText('Kim schreibt');await expect.poll(()=>state.requests.filter(r=>r.path.endsWith('/read/')).length).toBeGreaterThan(0);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Tippen');await expect.poll(()=>state.requests.filter(r=>r.path.endsWith('/typing/')&&r.body.active===true).length).toBeGreaterThan(0);
});

test('friend duels reuse game cards and blocking removes further controls',async({page})=>{
 const state=await boot(page);await openChat(page);await page.locator('.messenger-chat-title').click();await expect(page.getByRole('heading',{name:'Freundesduelle'})).toBeVisible();await expect(page.getByText('Just for fun – ohne Familienaufgaben oder Einsatz.')).toBeVisible();await expect(page.getByText('Aufgaben-Einsatz')).toHaveCount(0);await page.getByRole('button',{name:'Kontakt blockieren',exact:true}).click();const dialog=page.getByRole('alertdialog');await dialog.getByRole('button',{name:'Kontakt blockieren',exact:true}).click();await expect(page.getByText('Dieser Chat ist nur noch lesbar.')).toBeVisible();await expect(page.getByRole('button',{name:'Senden',exact:true})).toHaveCount(0);expect(state.chat.can_send).toBe(false);
});

for(const width of [320,390,1440])test(`messenger remains responsive and keyboard accessible at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:900});await boot(page);await openChat(page);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Keyboard');await page.getByRole('textbox',{name:'Nachricht',exact:true}).press('Enter');await expect(page.locator('.messenger-bubble.own')).toContainText('Keyboard');expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);for(const control of ['Senden','Sprachnachricht aufnehmen']){const box=await page.getByRole('button',{name:control,exact:true}).boundingBox();expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44)}const axe=await new AxeBuilder({page}).include('.messenger-page').analyze();expect(axe.violations.filter(x=>['critical','serious'].includes(x.impact))).toEqual([]);
});

test('personal account without family opens messenger and no family tools',async({page})=>{
 await boot(page,{familyless:true,language:'en'});await openChat(page);await expect(page.getByRole('button',{name:'Family notices',exact:true})).toHaveCount(0);await expect(page.locator('.global-create-fab')).toHaveCount(0);await expect(page.getByRole('textbox',{name:'Message',exact:true})).toBeVisible();if(await page.locator('.messenger-mobile-back').isVisible())await page.locator('.messenger-mobile-back').click();await expect(page.getByRole('button',{name:'Sign out',exact:true})).toBeVisible();
});

test('invitation token is removed from location and acceptance never joins a family',async({page})=>{
 await installApiMocks(page,{authenticated:false});let registered=null;await page.route('**/api/chat/invite/**',route=>{if(route.request().url().endsWith('/preview/'))return json(route,{sender_name:'Kim',status:'pending'});registered=route.request().postDataJSON();return json(route,{user_id:9,friendship_id:friendId},201)});await page.goto('/?page=inbox#chat-invite=signed-mailbox-token');await expect(page.getByRole('heading',{name:'Persönliche Chat-Einladung'})).toBeVisible();await expect(page).not.toHaveURL(/signed-mailbox-token/);await page.getByRole('button',{name:'Neues Konto anlegen',exact:true}).click();await page.getByRole('textbox',{name:'Anzeigename',exact:true}).fill('New friend');await page.getByLabel(/^Passwort/).fill('Correct-Horse-4218!');await page.getByRole('button',{name:'Konto anlegen und annehmen'}).click();await expect.poll(()=>registered).toMatchObject({token:'signed-mailbox-token',display_name:'New friend'});
});

test('200 percent zoom and reduced motion retain composer controls',async({page})=>{
 await page.setViewportSize({width:1440,height:1000});await page.emulateMedia({reducedMotion:'reduce'});await boot(page);await openChat(page);await page.evaluate(()=>document.documentElement.style.zoom='2');await expect(page.getByRole('textbox',{name:'Nachricht',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});

test('microphone is explicit and switching away stops all tracks',async({page})=>{
 await page.addInitScript(()=>{
  window.chatMic={requests:0,stops:0};
  const track={stop:()=>window.chatMic.stops++};
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{window.chatMic.requests++;return {getTracks:()=>[track]}}}});
  window.MediaRecorder=class{
   static isTypeSupported(type){return type.startsWith('audio/webm')}
   constructor(){this.state='inactive'}
   start(){this.state='recording'}
   stop(){this.state='inactive';this.onstop?.()}
  };
 });
 await boot(page);await openChat(page);expect(await page.evaluate(()=>window.chatMic.requests)).toBe(0);await page.getByRole('button',{name:'Sprachnachricht aufnehmen',exact:true}).click();await expect(page.getByRole('button',{name:'Aufnahme beenden',exact:true})).toBeVisible();expect(await page.evaluate(()=>window.chatMic.requests)).toBe(1);await page.locator('.messenger-chat-title').click();if(await page.locator('.messenger-mobile-back').isVisible())await page.locator('.messenger-mobile-back').click();else await page.getByRole('button',{name:'Freunde',exact:false}).first().click();await expect.poll(()=>page.evaluate(()=>window.chatMic.stops)).toBeGreaterThan(0);
});
