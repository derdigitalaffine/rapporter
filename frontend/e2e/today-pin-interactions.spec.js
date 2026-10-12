import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,{language='de',compact=false,multipleFamilies=false,hidden=false,sourceUnavailable=false}={}){
 const mock=await installApiMocks(page,{language});mock.todayLayout={version:2,revision:8,widgets:[{id:'pinboard',visible:!hidden,size:compact?'compact':'wide'}]};
 if(multipleFamilies)await page.route('**/api/families/',route=>route.fulfill({json:[mock.family,{...mock.family,id:'family-2',name:'Andere Familie'}]}));
 const state={keys:{},seen:false,revoked:false,error:0,reads:0,requests:[],gates:[],comments:[{id:'comment-old',body:'Nur im geöffneten Thread',author_name:'Sam',created_at:new Date().toISOString(),mine:false,can_edit:false,can_delete:false,reactions:[]}]};
 const summary=(id='pin-a')=>{const key=state.keys[id]||null;return {comment_count:id==='pin-a'?state.comments.length:1,has_unread_comments:id==='pin-a'?!state.seen:true,reactions:[{key:'thumbs_up',count:key==='thumbs_up'?3:2,mine:key==='thumbs_up'},...(key&&key!=='thumbs_up'?[{key,count:1,mine:true}]:[])],can_interact:true,muted:false}};
 const pins=()=>['pin-a','pin-b','pin-c','pin-d','pin-e'].filter(id=>!state.revoked||id!=='pin-a').map((id,index)=>({id,family:'family-1',text:`Punkt ${id}`,kind:'note',target:null,position:index,author:1,author_name:'Alex',images:[],can_interact:true,interaction:summary(id),...(sourceUnavailable&&id==='pin-a'?{kind:'document',text:'Private source title',target:{available:false,title:'Private source title'},images:[{url:'/private-image.png'}],can_interact:false,interaction:{comment_count:99,can_interact:false,reactions:[]}}:{})}));
 await page.route('**/api/board/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname;let body;try{body=req.postDataJSON()}catch{}state.requests.push({path,method:req.method(),body});
  if(path==='/api/board/'&&req.method()==='GET'){state.reads+=1;const rows=url.searchParams.get('family')==='family-2'?[]:pins(),status=state.error,gate=state.gates.shift();if(gate)await gate;return status?route.fulfill({status,json:{detail:'unavailable'}}):route.fulfill({json:{results:rows,count:rows.length,next:null}})}
  if(path.endsWith('/reaction/')&&req.method()==='PUT'){if(state.revoked)return route.fulfill({status:403,json:{detail:'unavailable'}});const id=path.split('/')[3];state.keys[id]=body.key;return route.fulfill({json:summary(id)})}
  if(path.endsWith('/mention-targets/'))return route.fulfill({json:[]});
  if(path.endsWith('/comments/')&&req.method()==='GET'){state.seen=true;return route.fulfill({json:{results:[...state.comments].reverse(),next:null}})}
  if(path.endsWith('/comments/')&&req.method()==='POST'){const row={id:`comment-${state.comments.length}`,body:body.body,author_name:'Alex',created_at:new Date().toISOString(),mine:true,can_edit:true,can_delete:true,reactions:[]};state.comments.push(row);return route.fulfill({status:201,json:{...row,interaction:summary()}})}
  return route.fulfill({status:404,json:{detail:'not found'}});
 });
 await page.goto('/?page=home');const widget=page.getByTestId('today-pinboard');if(hidden)await expect(widget).toHaveCount(0);else{await expect(widget.locator('[data-today-pin]')).toHaveCount(compact?2:4);await widget.scrollIntoViewIfNeeded()}return {state,mock,widget};
}

test('Today reuses canonical summary and one/two-tap reactions without changing manual order',async({page})=>{
 const {state,widget}=await boot(page,{compact:true});const cards=widget.locator('[data-today-pin]');expect(await cards.evaluateAll(rows=>rows.map(row=>row.dataset.todayPin))).toEqual(['pin-a','pin-b']);await expect(widget).not.toContainText('Nur im geöffneten Thread');const first=cards.first(),chip=first.getByRole('button',{name:'Passt, 2',exact:true});await chip.click();await expect(first.getByRole('button',{name:'Passt, 3',exact:true})).toHaveAttribute('aria-pressed','true');await expect(cards.nth(1).getByRole('button',{name:'Passt, 2',exact:true})).toHaveAttribute('aria-pressed','false');await first.getByRole('button',{name:'Passt, 3',exact:true}).click();await expect(chip).toHaveAttribute('aria-pressed','false');await first.getByRole('button',{name:'Reagieren',exact:true}).click();await first.getByRole('button',{name:'Herz',exact:true}).click();await expect(first.getByRole('button',{name:'Herz, 1',exact:true})).toHaveAttribute('aria-pressed','true');expect(state.requests.filter(row=>row.method==='PUT').map(row=>row.body.key)).toEqual(['thumbs_up',null,'heart']);expect(await cards.evaluateAll(rows=>rows.map(row=>row.dataset.todayPin))).toEqual(['pin-a','pin-b']);expect(state.requests.filter(row=>row.method==='GET'&&row.path.endsWith('/comments/'))).toHaveLength(0);expect(await widget.locator('button button,button a').count()).toBe(0);
});

test('one comment tap focuses the existing thread and commits its canonical count',async({page})=>{
 const {state,widget}=await boot(page,{compact:true});const first=widget.locator('[data-today-pin]').first(),trigger=first.getByRole('button',{name:/Kommentieren/});await expect(trigger).toHaveClass(/unread/);await trigger.click();const dialog=page.getByRole('dialog',{name:'Pin-Kommentare'});await expect(dialog.locator('textarea').last()).toBeFocused();await expect(dialog).toContainText('Nur im geöffneten Thread');await dialog.locator('textarea').last().fill('Kommentar aus Today');await dialog.getByRole('button',{name:'Senden',exact:true}).click();await expect(dialog).toContainText('Kommentar aus Today');expect(state.requests.filter(row=>row.method==='POST')).toHaveLength(1);expect(state.requests.find(row=>row.method==='POST').body.client_id).toMatch(/^[0-9a-f-]{36}$/);await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();await expect(trigger).toHaveAccessibleName('Kommentieren, 2 Kommentare');await expect(trigger).not.toHaveClass(/unread/);await expect(widget).not.toContainText('Kommentar aus Today');
});

test('denied reaction removes private content immediately and reloads only the canonical projection',async({page})=>{
 const {state,widget}=await boot(page);state.revoked=true;await widget.locator('[data-today-pin="pin-a"]').getByRole('button',{name:'Passt, 2',exact:true}).click();await expect(widget.locator('[data-today-pin="pin-a"]')).toHaveCount(0);await expect(widget).not.toContainText('Punkt pin-a');await expect.poll(()=>state.reads).toBeGreaterThan(1);await expect(widget.locator('[data-today-pin="pin-b"]')).toBeVisible();
});

test('transient reload retains rows with retry, denied retry clears previews and counts',async({page})=>{
 const {state,widget}=await boot(page);state.error=503;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(widget.getByRole('alert')).toContainText('Der letzte bestätigte Stand bleibt sichtbar.');await expect(widget).toContainText('Punkt pin-a');state.error=403;await widget.getByRole('button',{name:'Erneut laden',exact:true}).click();await expect(widget.getByRole('alert')).toContainText('Diese Pinnwand ist nicht mehr verfügbar.');await expect(widget.locator('[data-today-pin]')).toHaveCount(0);await expect(widget.getByRole('button',{name:/Kommentieren/})).toHaveCount(0);
});

test('late previous-family read cannot restore pin preview or interaction state',async({page})=>{
 const {state,widget}=await boot(page,{multipleFamilies:true});let release;state.gates.push(new Promise(resolve=>release=resolve));const baseline=state.reads;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect.poll(()=>state.reads).toBeGreaterThan(baseline);await page.locator('.family-switcher select').selectOption('family-2');await expect(page.locator('.family-switcher select')).toHaveValue('family-2');await expect(page.getByTestId('today-pinboard')).toContainText('Ersten wichtigen Punkt anpinnen');release();await expect(page.getByTestId('today-pinboard').locator('[data-today-pin]')).toHaveCount(0);await expect(page.getByTestId('today-pinboard')).not.toContainText('Punkt pin-a');
});

test('a delayed board read cannot restore an old summary after a confirmed reaction',async({page})=>{
 const {state,widget}=await boot(page,{compact:true});let release;state.gates.push(new Promise(resolve=>release=resolve));const baseline=state.reads;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect.poll(()=>state.reads).toBeGreaterThan(baseline);const first=widget.locator('[data-today-pin]').first();await first.getByRole('button',{name:'Passt, 2',exact:true}).click();await expect(first.getByRole('button',{name:'Passt, 3',exact:true})).toHaveAttribute('aria-pressed','true');release();await expect.poll(()=>state.reads).toBeGreaterThan(baseline+1);await expect(first.getByRole('button',{name:'Passt, 3',exact:true})).toHaveAttribute('aria-pressed','true');
});

test('logout invalidates a delayed board response and all private previews',async({page})=>{
 const {state,widget}=await boot(page,{compact:true});let release;state.gates.push(new Promise(resolve=>release=resolve));const baseline=state.reads;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect.poll(()=>state.reads).toBeGreaterThan(baseline);await page.evaluate(()=>{localStorage.removeItem('famuhle-session');window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:false}}))});await expect(widget.locator('[data-today-pin]')).toHaveCount(0);release();await expect(widget.locator('[data-today-pin]')).toHaveCount(0);await expect(page.getByText('Punkt pin-a',{exact:true})).toHaveCount(0);
});

test('source-unavailable shell exposes no stale title image or interaction count',async({page})=>{
 const {widget}=await boot(page,{sourceUnavailable:true});const first=widget.locator('[data-today-pin="pin-a"]');await expect(first).toContainText('Nicht mehr verfügbar');await expect(first).not.toContainText('Private source title');await expect(first.locator('img')).toHaveCount(0);await expect(first.locator('.pin-interaction-bar')).toHaveCount(0);await expect(first).not.toContainText('99');
});

test('saved hidden Pinboard never mounts its interaction consumer or changes preferences',async({page})=>{
 const {state,mock,widget}=await boot(page,{hidden:true});await expect(page.getByTestId('today-layout-edit')).toBeEnabled();await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(widget).toHaveCount(0);expect(state.reads).toBe(0);expect(mock.todayLayout.revision).toBe(8);expect(mock.todayLayout.widgets[0].visible).toBe(false);await page.reload();await expect(page.getByTestId('today-layout-edit')).toBeEnabled();await expect(widget).toHaveCount(0);expect(state.reads).toBe(0);
});

test('visual · compact Today pin interactions',async({page})=>{
 const {widget}=await boot(page,{compact:true});await page.evaluate(()=>document.fonts.ready);await expect(widget).toHaveScreenshot('today-pin-interactions.png',{animations:'disabled',caret:'hide'});
});

for(const [language,title,comment] of [['de','Pinnwand','Kommentieren'],['en','Pinboard','Comment'],['fr','Tableau familial','Commenter'],['nl','Prikbord','Opmerking'],['th','กระดานครอบครัว','แสดงความคิดเห็น']])test(`Today pin actions ${language} retain keyboard and responsive contracts`,async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});const {widget}=await boot(page,{language,compact:true});await expect(widget.getByRole('heading',{name:title,exact:true})).toBeVisible();for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)}await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.style.zoom='2');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.evaluate(()=>document.documentElement.style.zoom='1');const trigger=widget.locator('[data-today-pin]').first().getByRole('button',{name:new RegExp(comment)});expect((await trigger.boundingBox()).height).toBeGreaterThanOrEqual(44);await trigger.focus();await page.keyboard.press('Enter');await expect(page.getByRole('dialog').locator('textarea').last()).toBeFocused();await page.keyboard.press('Escape');await expect(trigger).toBeFocused();
});
