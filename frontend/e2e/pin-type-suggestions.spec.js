import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';
import {pinComposerCopy} from '../src/pin-composer-copy.js';

const LEGACY={task:'task',routine:'routine',calendar_event:'event',shopping_item:'shopping',shopping_list:'shopping_list',document:'document',note:'note_ref',trip:'trip'};
const storageKey=(user='1',member='member-1',family='family-1')=>'familyos-pin-types:v1:'+JSON.stringify([user,member,family]);
const form=page=>page.locator('.pin-composer');
const sourceButton=(page,key)=>form(page).getByRole('button',{name:'Private '+key+' source · Never store this preview',exact:true});
async function boot(page,{seed,language='de',user=1,delaySave}={}){
 const fixture=await installApiMocks(page,{language});
 const state={posts:[],reads:[],fail:false,fixture};
 if(seed)await page.addInitScript(({key,seed})=>{if(localStorage.getItem(key)===null)localStorage.setItem(key,JSON.stringify(seed))},{key:storageKey(),seed});
 if(user!==1)await page.route('**/api/auth/session/',route=>route.fulfill({json:{authenticated:true,user:{id:user,username:'sam'}}}));
 await page.route('**/api/board/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.pathname==='/api/board/picker/'){
   const key=url.searchParams.get('adapter_key');state.reads.push(key);
   return route.fulfill({json:{adapter_key:key,kind:LEGACY[key],page:1,page_size:20,has_next:false,results:[{id:'source-private-'+key,kind:LEGACY[key],title:'Private '+key+' source',subtitle:'Never store this preview',url:'/?page=example'}]}});
  }
  if(request.method()==='POST'){
   const body=request.postDataJSON();state.posts.push(body);
   if(delaySave)await delaySave;
   if(state.fail)return route.fulfill({status:400,json:{detail:'Save failed'}});
   return route.fulfill({status:201,json:{id:'pin-new',...body,target:null,visibility:'private',effective_scope:'private',images:[]}});
  }
  return route.fulfill({json:{count:0,next:null,results:[]}});
 });
 await page.goto('/?page=board');
 await openExisting(page,language);
 return state;
}
async function openExisting(page,language='de'){
 const w=pinComposerCopy(language);
 await page.getByRole('button',{name:language==='en'?'Pin something':'Anpinnen',exact:true}).click();
 await form(page).getByRole('button',{name:w.existing,exact:true}).click();
 await expect(form(page).locator('.pin-type-preference')).toBeVisible();
}
async function pin(page,group,key){
 await form(page).locator('.pin-source-groups').getByRole('button',{name:group,exact:true}).click();
 await sourceButton(page,key).click();
 await form(page).getByRole('button',{name:'Anpinnen',exact:true}).click();
 await expect(form(page)).toHaveCount(0);
}
async function prefs(page,key=storageKey()){return page.evaluate(key=>JSON.parse(localStorage.getItem(key)||'null'),key)}

test('recent types are explicit picker shortcuts without preselection or mutations',async({page})=>{
 const state=await boot(page,{seed:{enabled:true,types:['document','task','trip'],title:'Do not adopt private text'}});
 const recent=form(page).getByRole('group',{name:'Zuletzt verwendete Typen'});
 await expect(recent.locator('button')).toHaveCount(3);
 await expect(form(page).getByRole('button',{name:'Anpinnen',exact:true})).toBeDisabled();
 expect(state.posts).toEqual([]);
 await recent.getByRole('button',{name:'Dokumente',exact:true}).click();
 await expect(sourceButton(page,'document')).toBeVisible();
 await expect(form(page).getByRole('button',{name:'Anpinnen',exact:true})).toBeDisabled();
 expect(state.reads).toContain('document');expect(state.posts).toEqual([]);
});

test('successful reference pins learn only three deduplicated types, never content or IDs',async({page})=>{
 await boot(page);
 for(const [group,key] of [['Kalender','calendar_event'],['Dokumente','document'],['Weitere','note'],['To-dos','task']]){
  await pin(page,group,key);await openExisting(page);
 }
 expect(await prefs(page)).toEqual({enabled:true,types:['task','note','document']});
 const stored=await page.evaluate(key=>localStorage.getItem(key),storageKey());
 expect(stored).not.toMatch(/Private|source-private|Never store|visibility|target_id|family/);
 await pin(page,'Dokumente','document');expect(await prefs(page)).toEqual({enabled:true,types:['document','task','note']});
});

test('opt-out clears remembered types, survives reload and stops later learning',async({page})=>{
 await boot(page,{seed:{enabled:true,types:['document','trip']}});
 await form(page).locator('.pin-type-preference summary').click();
 await form(page).getByRole('checkbox',{name:'Zuletzt verwendete Typen anzeigen'}).uncheck();
 await expect(form(page).getByRole('group',{name:'Zuletzt verwendete Typen'})).toHaveCount(0);
 expect(await prefs(page)).toEqual({enabled:false,types:[]});
 await pin(page,'Kalender','calendar_event');expect(await prefs(page)).toEqual({enabled:false,types:[]});
 await page.reload();await openExisting(page);
 await form(page).locator('.pin-type-preference summary').click();
 await expect(form(page).getByRole('checkbox',{name:'Zuletzt verwendete Typen anzeigen'})).not.toBeChecked();
 await form(page).getByRole('checkbox',{name:'Zuletzt verwendete Typen anzeigen'}).check();
 expect(await prefs(page)).toEqual({enabled:true,types:[]});
});

test('failed saves retain selection and learn nothing until successful retry',async({page})=>{
 const state=await boot(page);state.fail=true;
 await sourceButton(page,'task').click();
 await form(page).getByRole('button',{name:'Anpinnen',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Save failed');expect(await prefs(page)).toBeNull();
 await expect(form(page).getByRole('button',{name:'Anpinnen',exact:true})).toBeEnabled();
 state.fail=false;await form(page).getByRole('button',{name:'Anpinnen',exact:true}).click();await expect(form(page)).toHaveCount(0);
 expect(await prefs(page)).toEqual({enabled:true,types:['task']});
});

test('another verified user cannot adopt the first user type profile',async({page})=>{
 await boot(page,{user:2,seed:{enabled:true,types:['document','trip']}});
 await expect(form(page).getByRole('group',{name:'Zuletzt verwendete Typen'})).toHaveCount(0);
 await pin(page,'Kalender','calendar_event');
 expect(await prefs(page)).toEqual({enabled:true,types:['document','trip']});
 expect(await prefs(page,storageKey('2','member-2'))).toEqual({enabled:true,types:['calendar_event']});
});

test('opt-out remains effective in this session when browser storage writes fail',async({page})=>{
 await boot(page,{seed:{enabled:true,types:['document']}});
 await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw new DOMException('Storage full','QuotaExceededError')}});
 await form(page).locator('.pin-type-preference summary').click();
 await form(page).getByRole('checkbox',{name:'Zuletzt verwendete Typen anzeigen'}).uncheck();
 await expect(form(page).getByRole('group',{name:'Zuletzt verwendete Typen'})).toHaveCount(0);
 await pin(page,'Kalender','calendar_event');await openExisting(page);
 await form(page).locator('.pin-type-preference summary').click();
 await expect(form(page).getByRole('checkbox',{name:'Zuletzt verwendete Typen anzeigen'})).not.toBeChecked();
});

test('auth loss invalidates suggestions and a late save cannot learn old types',async({page})=>{
 let release;const delaySave=new Promise(resolve=>{release=resolve});
 const state=await boot(page,{delaySave});
 await sourceButton(page,'task').click();
 await form(page).getByRole('button',{name:'Anpinnen',exact:true}).click();await expect.poll(()=>state.posts.length).toBe(1);
 await page.evaluate(()=>{localStorage.removeItem('famuhle-session');window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:false}}))});
 await expect(form(page).locator('.pin-type-preference')).toHaveCount(0);
 const settled=page.waitForResponse(response=>response.url().endsWith('/api/board/')&&response.request().method()==='POST');release();await settled;await page.waitForLoadState('networkidle');
 expect(await prefs(page)).toBeNull();await expect(form(page).getByRole('button',{name:'Anpinnen',exact:true})).toBeDisabled();
});

test('family switch fences a late create result and does not learn in either family',async({page})=>{
 let release;const delaySave=new Promise(resolve=>{release=resolve});
 const state=await boot(page,{delaySave});
 const other={...state.fixture.family,id:'family-2',name:'Andere Familie',memberships:[{id:'member-other',user:1,role:'owner'}]};
 await page.route('**/api/families/',route=>route.fulfill({json:[state.fixture.family,other]}));
 await page.reload();await openExisting(page);
 await sourceButton(page,'task').click();await form(page).getByRole('button',{name:'Anpinnen',exact:true}).click();await expect.poll(()=>state.posts.length).toBe(1);
 await page.locator('.family-switcher select').selectOption('family-2');
 const settled=page.waitForResponse(response=>response.url().endsWith('/api/board/')&&response.request().method()==='POST');release();await settled;await page.waitForLoadState('networkidle');
 expect(await prefs(page)).toBeNull();expect(await prefs(page,storageKey('1','member-other','family-2'))).toBeNull();
});

test('English keyboard suggestions keep 44px targets, 320px/200% and accessibility',async({page})=>{
 await page.setViewportSize({width:320,height:844});
 await boot(page,{language:'en',seed:{enabled:true,types:['document','task','trip']}});
 const recent=form(page).getByRole('group',{name:'Recently used types'});
 for(const button of await recent.locator('button').all())expect((await button.boundingBox()).height).toBeGreaterThanOrEqual(44);
 await recent.getByRole('button',{name:'Documents',exact:true}).focus();await page.keyboard.press('Enter');
 await expect(sourceButton(page,'document')).toBeVisible();
 await form(page).locator('.pin-type-preference summary').focus();await page.keyboard.press('Enter');
 await expect(form(page).getByRole('checkbox',{name:'Show recently used types'})).toBeVisible();
 await page.evaluate(()=>document.documentElement.style.fontSize='200%');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
 const accessibility=await new AxeBuilder({page}).include('.pin-composer').analyze();expect(accessibility.violations).toEqual([]);
});

for(const language of ['fr','nl','th'])test(`suggestion controls use ${language} copy`,async({page})=>{
 await boot(page,{language,seed:{enabled:true,types:['document']}});const w=pinComposerCopy(language);
 await expect(form(page).getByRole('group',{name:w.recent})).toBeVisible();await form(page).locator('.pin-type-preference summary').click();
 await expect(form(page).getByRole('checkbox',{name:w.showRecent})).toBeChecked();await expect(form(page).getByText(w.recentHint,{exact:true})).toBeVisible();
});
