import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';

const pin=(id,text,extra={})=>({id,family:'family-1',kind:'note',text,target:null,images:[],visibility:'family',effective_scope:'family',author:1,author_name:'Alex',created_at:'2026-10-13T08:00:00Z',can_change_pin_visibility:true,can_delete:true,can_reorder:true,can_interact:false,...extra});
async function boot(page,{language='de',rows=[pin('first','Erste Karte'),pin('second','Zweite Karte')],multipleFamilies=false}={}){
 const mocks=await installApiMocks(page,{language});
 if(multipleFamilies)await page.route('**/api/families/',route=>route.fulfill({json:[mocks.family,{...mocks.family,id:'family-2',name:'Andere Familie'}]}));
 const state={rows,requests:[]};
 await page.route('**/api/board/**',route=>{
  const req=route.request(),url=new URL(req.url()),method=req.method();
  if(method==='GET')return route.fulfill({json:{next:null,results:url.searchParams.get('family')==='family-2'?[]:state.rows}});
  const body=method==='POST'?req.postDataJSON():null;state.requests.push({method,body});
  if(url.pathname==='/api/board/reorder/'){state.rows=body.ids.map(id=>state.rows.find(row=>row.id===id));return route.fulfill({json:state.rows})}
  if(method==='DELETE'){state.rows=state.rows.filter(row=>!url.pathname.includes(`/${row.id}/`));return route.fulfill({status:204,body:''})}
  return route.fulfill({status:405,json:{detail:'unexpected'}});
 });
 await page.goto('/?page=board');await expect(page.locator('.pin-card')).toHaveCount(rows.length);return state;
}
const more=(page,id='first')=>page.locator(`#pin-${id} summary`);
async function move(page,id='first',direction='Weiter nach hinten'){
 await more(page,id).click();await page.locator(`#pin-${id}`).getByRole('button',{name:new RegExp(`^${direction}:`)}).click();
}

test('canonical source opens directly; rare actions are disclosed and Escape restores card focus',async({page})=>{
 const row=pin('first','Kurze Beschriftung',{kind:'note_ref',effective_scope:'private',target:{available:true,title:'Quelle',url:'/?page=notes&note=source',can_share_source:true,source_share_url:'/?page=notes&note=source&share=1'}});
 await boot(page,{rows:[row]});const card=page.locator('#pin-first');await expect(card.getByRole('link',{name:'Quelle',exact:true})).toHaveAttribute('href',row.target.url);await expect(card).toContainText('Nur mich');await expect(card).toContainText('Kurze Beschriftung');
 await expect(card.getByRole('button',{name:'Bearbeiten',exact:true})).toBeHidden();await more(page).focus();await page.keyboard.press('Enter');await expect(card.getByRole('link',{name:'Quelle zusätzlich freigeben'})).toHaveAttribute('href',row.target.source_share_url);
 await card.getByRole('button',{name:'Bearbeiten',exact:true}).focus();await page.keyboard.press('Escape');await expect(more(page)).toBeFocused();await expect(card.locator('details')).not.toHaveAttribute('open','');
});

test('keyboard reorder keeps stable focus and sends canonical ordered IDs',async({page})=>{
 const state=await boot(page);await more(page).focus();await page.keyboard.press('Enter');const later=page.locator('#pin-first').getByRole('button',{name:'Weiter nach hinten: Erste Karte'});await later.focus();await page.keyboard.press('Enter');
 await expect(page.locator('.pin-card').first()).toHaveAttribute('id','pin-second');await expect(more(page)).toBeFocused();await expect.poll(()=>state.requests.length).toBe(1);expect(state.requests[0].body).toEqual({family:'family-1',ids:['second','first']});
 await page.reload();await expect(page.locator('.pin-card').first()).toHaveAttribute('id','pin-second');
});

test('failed reorder rolls back without duplicate mutations while pending',async({page})=>{
 await boot(page);let release,requested=false;const gate=new Promise(resolve=>release=resolve);let count=0;
 await page.route('**/api/board/reorder/',async route=>{requested=true;count++;await gate;return route.fulfill({status:503,json:{detail:'Sortierung nicht gespeichert'}})});
 await move(page);await expect.poll(()=>requested).toBe(true);await expect(page.locator('.pin-card').first()).toHaveAttribute('id','pin-second');await more(page,'second').click();await expect(page.locator('#pin-second').getByRole('button',{name:/Weiter nach hinten:/})).toBeDisabled();release();
 await expect(page.locator('.pin-card').first()).toHaveAttribute('id','pin-first');await expect(page.getByRole('alert')).toContainText('Sortierung nicht gespeichert');expect(count).toBe(1);
});

test('unavailable source never renders stale content or interaction metadata',async({page})=>{
 await boot(page,{rows:[pin('first','VERTRAULICHER TEXT',{kind:'document',target:{available:false,title:'GEHEIMER TITEL',subtitle:'PRIVATE METADATEN',url:'/?page=documents',can_share_source:true,source_share_url:'/?page=documents&share=1'},author_name:'GEHEIMER AUTOR',images:[{id:'secret',url:'/private-photo.png'}],can_interact:true,interaction:{comment_count:99,can_interact:true}})]});
 const card=page.locator('#pin-first');await expect(card).toContainText('Nicht mehr verfügbar');await expect(card).not.toContainText(/VERTRAULICH|GEHEIM|PRIVATE|99/);await expect(card.locator('img,.pin-author,.pin-interactions')).toHaveCount(0);await expect(card.locator('a')).toHaveCount(0);await more(page).click();await expect(card.getByRole('button',{name:'Entfernen',exact:true})).toBeVisible();await expect(card.getByRole('link',{name:'Quelle zusätzlich freigeben'})).toHaveCount(0);
});

test('server capabilities govern every card action',async({page})=>{
 await boot(page,{rows:[pin('first','Nur lesen',{can_change_pin_visibility:false,can_delete:false,can_reorder:false})]});await expect(more(page)).toHaveCount(0);await expect(page.locator('#pin-first button')).toHaveCount(0);
});

for(const [language,label] of [['en','More'],['fr','Plus'],['nl','Meer'],['th','เพิ่มเติม']])test(`card actions use ${language} copy`,async({page})=>{
 await boot(page,{language});await expect(more(page)).toHaveAccessibleName(`${label}: Erste Karte`);await more(page).click();await expect(page.locator('#pin-first .todo-actions-popover')).toBeVisible();
});

test('card actions reflow at 320/390/768/1440 and 200% with touch targets and no axe violations',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});await boot(page);
 for(const width of [320,390,768,1440]){
  await page.setViewportSize({width,height:844});await more(page).click();const summaryBox=await more(page).boundingBox();expect(summaryBox.width).toBeGreaterThanOrEqual(44);expect(summaryBox.height).toBeGreaterThanOrEqual(44);
  for(const button of await page.locator('#pin-first .todo-actions-popover button').all()){const box=await button.boundingBox();expect(box.height).toBeGreaterThanOrEqual(44)}
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.keyboard.press('Escape');
 }
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.style.fontSize='200%');await more(page).click();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.keyboard.press('Escape');
 const result=await new AxeBuilder({page}).include('.pinboard-grid').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();expect(result.violations).toEqual([]);
});

for(const action of ['reorder','delete'])test(`late ${action} failure cannot restore pins after family switch`,async({page})=>{
 await boot(page,{multipleFamilies:true});let release,requested=false;const gate=new Promise(resolve=>release=resolve);
 await page.route(action==='reorder'?'**/api/board/reorder/':'**/api/board/first/',async route=>{requested=true;await gate;return route.fulfill({status:503,json:{detail:'OLD FAMILY ERROR'}})});
 if(action==='reorder')await move(page);else{await more(page).click();await page.locator('#pin-first').getByRole('button',{name:'Entfernen',exact:true}).click();await page.getByRole('alertdialog').getByRole('button',{name:'Entfernen',exact:true}).click()}
 await expect.poll(()=>requested).toBe(true);await page.locator('.family-switcher select').selectOption('family-2');await expect(page.locator('.pin-card')).toHaveCount(0);release();
 await page.locator('.bottom-nav button').filter({hasText:'Mehr'}).click();await page.getByRole('button',{name:'Pinnwand',exact:true}).click();await expect(page.locator('.pin-card')).toHaveCount(0);await expect(page.getByText('OLD FAMILY ERROR')).toHaveCount(0);
});

test('late reorder rollback cannot restore pins after auth loss',async({page})=>{
 await boot(page);let release,requested=false;const gate=new Promise(resolve=>release=resolve);
 await page.route('**/api/board/reorder/',async route=>{requested=true;await gate;return route.fulfill({status:503,json:{detail:'OLD AUTH ERROR'}})});await move(page);await expect.poll(()=>requested).toBe(true);
 await page.evaluate(()=>{localStorage.removeItem('famuhle-session');window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:false}}))});await expect(page.locator('.pin-card')).toHaveCount(0);release();await expect(page.getByText('OLD AUTH ERROR')).toHaveCount(0);
});

test('reorder rollback cannot restore a source revoked during an interaction',async({page})=>{
 const state=await boot(page,{rows:[pin('first','Erste Karte',{can_interact:true,interaction:{can_interact:true,comment_count:0,reactions:[]}}),pin('second','Zweite Karte')]});
 let release,requested=false;const gate=new Promise(resolve=>release=resolve);
 await page.route('**/api/board/reorder/',async route=>{requested=true;await gate;return route.fulfill({status:503,json:{detail:'Reorder failed'}})});
 await page.route('**/api/board/first/reaction/',route=>{state.rows=state.rows.filter(row=>row.id!=='first');return route.fulfill({status:403,json:{detail:'revoked'}})});
 await move(page);await expect.poll(()=>requested).toBe(true);await page.locator('#pin-first').getByRole('button',{name:/Reaktion, 0.*Reagieren/}).click();await page.getByRole('button',{name:'Passt',exact:true}).click();
 await expect(page.locator('#pin-first')).toHaveCount(0);const reload=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/board/'&&response.request().method()==='GET');release();await reload;await expect(page.locator('.pin-card')).toHaveCount(1);await expect(page.locator('#pin-second')).toBeVisible();await expect(page.locator('#pin-first')).toHaveCount(0);
});
