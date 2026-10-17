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
    const msg={...rows[0],id:'message-'+(rows.length+1),sender_id:1,sender_name:'Alex',body:text,location:JSON.parse(raw.match(/name="location"\r\n\r\n([^\r]+)/)?.[1]||'null'),client_id:key,sequence:++chat.revision,event_sequence:chat.revision};rows.push(msg);chat.last_message=msg;return json(route,msg,201)
   }
   const q=url.searchParams.get('q'),before=Number(url.searchParams.get('before')||Infinity),after=Number(url.searchParams.get('after')||0);const matches=rows.filter(row=>(!q||row.body.includes(q))&&row.sequence<before&&row.event_sequence>after);return json(route,{results:after?matches:matches.slice(-50),cursor:chat.revision,has_more:!after&&matches.length>50,before:matches.at(-50)?.sequence||1,conversation:chat})
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
async function openChat(page){await page.locator('.messenger-chat-row').click();await expect(page.locator('.messenger-bubble').first()).toContainText('Hallo aus der anderen Familie')}

test('personal chat sends canonical retry-safe message without legacy family notices',async({page})=>{
 const state=await boot(page);await openChat(page);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Hallo Kim');await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.locator('.messenger-bubble.own')).toContainText('Hallo Kim');await expect(page.getByRole('textbox',{name:'Nachricht',exact:true})).toHaveValue('');expect(state.requests.some(r=>r.path==='/api/inbox/'&&r.method==='POST')).toBe(false);if(await page.locator('.messenger-mobile-back').isVisible())await page.locator('.messenger-mobile-back').click();await expect(page.getByRole('button',{name:'Familien-Mitteilungen',exact:true})).toHaveCount(0);
});

test('send failure retains draft and stable retry UUID',async({page})=>{
 const state=await boot(page,{failSend:true});await openChat(page);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Retry me');await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Nicht gesendet');await expect(page.getByRole('textbox',{name:'Nachricht',exact:true})).toHaveValue('Retry me');state.failSend=false;await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.locator('.messenger-bubble.own')).toContainText('Retry me');expect(state.rows.at(-1).client_id).toMatch(/^[0-9a-f-]{36}$/);
});

test('email contact invitation and acceptance use explicit personal endpoints',async({page})=>{
 const state=await boot(page);await page.getByRole('button',{name:/Freunde/}).first().click();await page.getByRole('textbox',{name:'E-Mail-Adresse',exact:true}).fill('outside@example.com');await page.getByRole('button',{name:'Einladung senden',exact:true}).click();await expect(page.getByRole('status')).toContainText('Einladung gesendet');expect(state.requests.find(r=>r.path==='/api/chat/invitations/'&&r.method==='POST').body).toMatchObject({email:'outside@example.com'});await page.getByRole('button',{name:'Annehmen',exact:true}).click();await expect(page.getByRole('heading',{name:'Kontaktanfragen'})).toHaveCount(0);expect(state.requests.some(r=>r.path.includes('/families/')&&r.method==='POST')).toBe(false);
});

test('typing and read receipts render only inside chosen chat',async({page})=>{
 const state=await boot(page);state.chat.typing=[{id:9,display_name:'Kim'}];await openChat(page);await expect(page.locator('.messenger-chat-title')).toContainText('Kim schreibt');await expect.poll(()=>state.requests.filter(r=>r.path.endsWith('/read/')).length).toBeGreaterThan(0);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Tippen');await expect.poll(()=>state.requests.filter(r=>r.path.endsWith('/typing/')&&r.body.active===true).length).toBeGreaterThan(0);
});

test('friend duels reuse game cards and blocking removes further controls',async({page})=>{
 const state=await boot(page);await openChat(page);await page.locator('.messenger-chat-title').click();await expect(page.getByRole('heading',{name:'Freundesduelle'})).toBeVisible();await expect(page.getByText('Just for fun – ohne Familienaufgaben oder Einsatz.')).toBeVisible();await expect(page.getByText('Aufgaben-Einsatz')).toHaveCount(0);await page.getByRole('button',{name:'Kontakt blockieren',exact:true}).click();const dialog=page.getByRole('alertdialog');await dialog.getByRole('button',{name:'Kontakt blockieren',exact:true}).click();await expect(page.getByText('Dieser Chat ist nur lesbar.')).toBeVisible();await expect(page.getByRole('button',{name:'Senden',exact:true})).toHaveCount(0);expect(state.chat.can_send).toBe(false);
});

for(const width of [320,390,1440])test(`messenger remains responsive and keyboard accessible at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:900});await boot(page);await openChat(page);await page.getByRole('textbox',{name:'Nachricht',exact:true}).fill('Keyboard');await page.getByRole('textbox',{name:'Nachricht',exact:true}).press('Enter');await expect(page.locator('.messenger-bubble.own')).toContainText('Keyboard');expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);expect((await page.getByRole('textbox',{name:'Nachricht',exact:true}).boundingBox()).width).toBeGreaterThanOrEqual(100);await expect(page.locator('.global-create-fab')).toBeHidden();for(const control of ['Senden','Sprachnachricht aufnehmen']){const box=await page.getByRole('button',{name:control,exact:true}).boundingBox();expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44)}const axe=await new AxeBuilder({page}).include('.messenger-page').analyze();expect(axe.violations.filter(x=>['critical','serious'].includes(x.impact))).toEqual([]);
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

test('chat history scrolls independently and the composer stays above navigation after resize',async({page},testInfo)=>{
 const state=await boot(page);
 const first=state.rows[0];
 state.rows.push(...Array.from({length:50},(_,index)=>({...first,id:`history-${index}`,sequence:index+2,event_sequence:index+2,sender_id:index%2?1:9,body:`Nachricht ${index+2}: Wir treffen uns morgen am Spielplatz.`,created_at:new Date(Date.now()-((50-index)*60_000)).toISOString()})));
 state.chat.revision=51;
 await openChat(page);
 const history=page.locator('.messenger-history'),composer=page.locator('.messenger-composer'),nav=page.locator('.bottom-nav');
 await expect.poll(()=>history.evaluate(el=>el.scrollHeight-el.clientHeight)).toBeGreaterThan(300);
 const before=await composer.boundingBox();
 await history.evaluate(el=>el.scrollTop=0);
 await history.hover();await page.mouse.wheel(0,-700);
 expect(await page.evaluate(()=>window.scrollY)).toBe(0);
 expect((await composer.boundingBox()).y).toBeCloseTo(before.y,0);
 expect((await composer.boundingBox()).y+before.height).toBeLessThanOrEqual((await nav.boundingBox()).y+1);
 expect((await nav.boundingBox()).y-before.y-before.height).toBeLessThanOrEqual(14);
 await page.screenshot({path:`/tmp/familyos-messenger-${testInfo.project.name}.png`});
 const field=page.getByRole('textbox',{name:'Nachricht',exact:true});
 await field.fill('Eine Nachricht\nmit mehreren Zeilen\nund etwas mehr Platz.');
 expect((await field.boundingBox()).height).toBeGreaterThan(60);
 await page.setViewportSize({width:390,height:440});
 await expect(field).toBeVisible();
 await expect.poll(async()=>{const box=await composer.boundingBox(),navBox=await nav.boundingBox();return box.y+box.height-navBox.y}).toBeLessThanOrEqual(1);
 expect((await history.boundingBox()).height).toBeGreaterThan(30);
 expect(await page.evaluate(()=>document.documentElement.scrollHeight-window.innerHeight)).toBeLessThanOrEqual(1);
});

test('visual viewport keyboard resize keeps editable messenger visible without lifting app navigation',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.addInitScript(()=>{
  const viewport=new EventTarget();
  Object.assign(viewport,{height:844,width:390,offsetTop:0,offsetLeft:0,scale:1});
  Object.defineProperty(window,'visualViewport',{configurable:true,value:viewport});
 });
 await boot(page);await openChat(page);
 const field=page.getByRole('textbox',{name:'Nachricht',exact:true});
 await field.focus();
 await page.evaluate(()=>{Object.assign(window.visualViewport,{height:440,offsetTop:20});window.visualViewport.dispatchEvent(new Event('resize'));window.visualViewport.dispatchEvent(new Event('scroll'))});
 const root=page.locator('html'),nav=page.locator('.bottom-nav'),composer=page.locator('.messenger-composer'),shell=page.locator('.messenger-shell');
 await expect(root).toHaveAttribute('data-app-keyboard','');
 await expect(nav).toBeHidden();
 await expect.poll(()=>shell.evaluate(el=>parseFloat(getComputedStyle(el).paddingBottom))).toBe(0);
 const shellBox=await shell.boundingBox();
 expect(shellBox.y).toBeCloseTo(20,0);
 expect(shellBox.height).toBeCloseTo(440,0);
 const composerBox=await composer.boundingBox();
 expect(composerBox.y+composerBox.height).toBeLessThanOrEqual(461);
 await expect(field).toBeVisible();
 await page.evaluate(()=>{Object.assign(window.visualViewport,{height:844,offsetTop:0});window.visualViewport.dispatchEvent(new Event('resize'))});
 await expect(root).not.toHaveAttribute('data-app-keyboard','');
 await expect(nav).toBeVisible();
 await expect.poll(async()=>{const box=await nav.boundingBox();return box.y+box.height}).toBeCloseTo(844,0);
 await page.evaluate(()=>{Object.assign(window.visualViewport,{height:422,offsetTop:80,scale:2});window.visualViewport.dispatchEvent(new Event('resize'))});
 await expect.poll(()=>shell.evaluate(el=>el.getBoundingClientRect().height)).toBe(844);
 await expect(root).not.toHaveAttribute('data-app-keyboard','');
 await expect(nav).toBeVisible();
});

test('main navigation remains pinned while transformed page content scrolls',async({page})=>{
 await boot(page);
 await page.locator('.bottom-nav').getByRole('button',{name:'Heute',exact:true}).click();
 await expect(page.locator('main[data-page="home"]')).toBeVisible();
 const nav=page.locator('.bottom-nav'),before=await nav.boundingBox();
 await page.locator('.app-shell').evaluate(el=>{el.style.transform='translateZ(0)';el.style.minHeight='2500px'});
 await page.evaluate(()=>window.scrollTo(0,900));
 await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBeGreaterThan(500);
 const after=await nav.boundingBox();
 expect(after.y).toBeCloseTo(before.y,0);
 expect(after.y+after.height).toBeCloseTo(page.viewportSize().height,0);
 await nav.getByRole('button',{name:'To-dos',exact:true}).click();
 await expect(page.locator('main[data-page="todo"]')).toBeVisible();
});

test('message dates and empty search results are readable without losing the draft',async({page})=>{
 await boot(page);await openChat(page);
 await expect(page.locator('.messenger-day')).toHaveCount(1);
 const field=page.getByRole('textbox',{name:'Nachricht',exact:true});await field.fill('Mein Entwurf');
 await page.locator('.messenger-chat-head').getByRole('button',{name:'Nachrichten durchsuchen',exact:true}).click();
 await page.getByRole('searchbox',{name:'Nachrichten durchsuchen',exact:true}).fill('not-in-chat');
 await page.locator('.messenger-search').getByRole('button',{name:'Nachrichten durchsuchen',exact:true}).click();
 await expect(page.getByText('Keine passenden Nachrichten.',{exact:true})).toBeVisible();
 await expect(field).toHaveValue('Mein Entwurf');
 await page.getByRole('searchbox',{name:'Nachrichten durchsuchen',exact:true}).fill('');
 await expect(page.locator('.messenger-bubble')).toContainText('Hallo aus der anderen Familie');
 await expect(field).toHaveValue('Mein Entwurf');
});

test('landscape messenger preserves composer space and long contact titles stay bounded',async({page})=>{
 await page.setViewportSize({width:844,height:390});
 const state=await boot(page);state.chat.title='Kim mit einem sehr langen Namen und weiteren Familienmitgliedern';
 await openChat(page);
 const nav=await page.locator('.bottom-nav').boundingBox(),composer=await page.locator('.messenger-composer').boundingBox();
 expect(composer.y+composer.height).toBeLessThanOrEqual(nav.y+1);
 expect((await page.locator('.messenger-history').boundingBox()).height).toBeGreaterThan(80);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);
 await expect(page.locator('.messenger-chat-title strong')).toContainText(state.chat.title);
});

test('dark messenger and main navigation use the current surface colors accessibly',async({page},testInfo)=>{
 await boot(page);await openChat(page);
 await page.evaluate(()=>{document.documentElement.dataset.colorProfile='green-dark';document.documentElement.style.colorScheme='dark'});
 await expect.poll(()=>page.locator('.bottom-nav').evaluate(el=>getComputedStyle(el).backgroundColor)).toBe('rgb(13, 24, 22)');
 const axe=await new AxeBuilder({page}).include('.messenger-page').include('.bottom-nav').analyze();
 expect(axe.violations.filter(x=>['critical','serious'].includes(x.impact))).toEqual([]);
 await page.screenshot({path:`/tmp/familyos-messenger-dark-${testInfo.project.name}.png`});
});

test('location requires explicit capture, review and send; retry preserves point and key',async({page})=>{
 await page.addInitScript(()=>{window.geoRequests=0;Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:success=>{window.geoRequests++;success({coords:{latitude:52.52,longitude:13.405,accuracy:12}})}}})});
 const state=await boot(page,{failSend:true});await openChat(page);
 await page.getByRole('button',{name:'Standort',exact:true}).click();
 expect(await page.evaluate(()=>window.geoRequests)).toBe(0);
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Standort ermitteln',exact:true}).click();
 await expect(dialog).toContainText('52.52000');expect(state.rows).toHaveLength(1);
 await dialog.getByRole('button',{name:'Zur Nachricht hinzufügen'}).click();await expect(dialog).toHaveCount(0);
 await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Nicht gesendet');
 await expect(page.locator('.messenger-location-draft')).toContainText('52.52000');
 state.failSend=false;await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.locator('.messenger-bubble.own')).toContainText('In OpenStreetMap öffnen');expect(state.rows.at(-1).location).toEqual({latitude:52.52,longitude:13.405,accuracy:12});
 await expect(page.locator('.messenger-location-draft')).toHaveCount(0);
});

test('location denial can be retried and cancel never sends',async({page})=>{
 await page.addInitScript(()=>{Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(_success,error)=>error({code:1})}})});
 const state=await boot(page);await openChat(page);const trigger=page.getByRole('button',{name:'Standort',exact:true});await trigger.click();
 await page.getByRole('button',{name:'Standort ermitteln',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Standortfreigabe abgelehnt');
 await expect(page.getByRole('button',{name:'Zur Nachricht hinzufügen'})).toBeDisabled();await page.getByRole('dialog').press('Escape');await expect(trigger).toBeFocused();expect(state.rows).toHaveLength(1);
});

test('older history preserves anchor and new messages do not interrupt reading',async({page})=>{
 const state=await boot(page),first=state.rows[0];
 state.rows.push(...Array.from({length:100},(_,i)=>({...first,id:`older-${i}`,sequence:i+2,event_sequence:i+2,body:`History ${i+2}`})));state.chat.revision=101;
 await page.locator('.messenger-chat-row').click();const history=page.locator('.messenger-history');
 await history.evaluate(node=>{node.scrollTop=0});
 const anchor=page.locator('.messenger-bubble').first(),text=await anchor.textContent(),top=(await anchor.boundingBox()).y;
 await page.getByRole('button',{name:'Ältere Nachrichten',exact:true}).click();
 await expect(page.locator('.messenger-bubble')).toHaveCount(100);
 const same=page.locator('.messenger-bubble').filter({hasText:text}).first();expect(Math.abs((await same.boundingBox()).y-top)).toBeLessThan(3);
 const position=await history.evaluate(node=>node.scrollTop);
 state.rows.push({...first,id:'new-live',sequence:102,event_sequence:102,body:'Neue Live-Nachricht'});state.chat.revision=102;
 await expect(page.getByRole('button',{name:'Neue Nachrichten'})).toBeVisible();expect(Math.abs(await history.evaluate(node=>node.scrollTop)-position)).toBeLessThan(3);
 await page.getByRole('button',{name:'Neue Nachrichten'}).click();await expect(page.getByText('Neue Live-Nachricht')).toBeInViewport();
});
