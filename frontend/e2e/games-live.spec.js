import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const match=(id='game-rps',game_type='rps')=>({id,family:'family-1',game_type,status:'active',am_challenger:true,can_accept:false,can_cancel:false,is_my_turn:true,challenger:{id:'member-1',user:1,display_name:'Alex'},opponent:{id:'member-2',user:2,display_name:'Sam'},rps:game_type==='rps'?{current_round:1,round_count:3,rounds:[{number:1,submitted_by_me:false,resolved:false}]}:null,battleship:game_type==='battleship'?{phase:'setup',my_fleet_confirmed:false,my_ships:[],shots:[]}:null});
const clone=value=>JSON.parse(JSON.stringify(value));
async function boot(page,{home=false,language='de',hiddenGames=false,multipleFamilies=false}={}){
 const mock=await installApiMocks(page,{language});
 if(hiddenGames)mock.todayLayout={version:2,revision:17,widgets:[{id:'todo',visible:true,size:'compact'},{id:'games',visible:false,size:'compact'},{id:'focus',visible:false,size:'wide'}]};
 if(multipleFamilies)await page.route('**/api/families/',route=>route.fulfill({json:[mock.family,{...mock.family,id:'family-2',name:'Andere Familie',memberships:mock.memberships.map(row=>({...row,family:'family-2'}))}]}));
 const state={matches:[match(),match('game-fleet','battleship')],reads:0,active:0,maxActive:0,errors:0,gates:[],writes:[],layoutWrites:[],taskReads:0};
 await page.route('**/api/today-layout/**',route=>{if(route.request().method()==='PUT')state.layoutWrites.push(route.request().postDataJSON());return route.fulfill({json:mock.todayLayout})});
 await page.route('**/api/tasks/?**',route=>{state.taskReads+=1;return route.fulfill({json:mock.tasks})});
 await page.route('**/api/games/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname;
  if(request.method()==='GET'){
   state.reads+=1;state.active+=1;state.maxActive=Math.max(state.maxActive,state.active);const rows=url.searchParams.get('family')==='family-2'?[]:clone(state.matches),status=state.errors,gate=state.gates.shift();
   try{if(gate)await gate;return status?route.fulfill({status,json:{detail:'temporary failure'}}):route.fulfill({json:path.endsWith('/summary/')?{actionable:rows,recent:[]}:rows})}finally{state.active-=1}
  }
  const body=request.postDataJSON();state.writes.push({path,body});if(path.endsWith('/rps/choice/')){state.matches[0].rps.rounds[0].submitted_by_me=true;return route.fulfill({json:clone(state.matches[0])})}
  return route.fulfill({status:404,json:{detail:'not found'}});
 });
 await page.goto(home?'/?page=home':'/?page=games');
 if(home)await expect(page.getByTestId('today-layout-edit')).toBeEnabled();
 if(home&&!hiddenGames){await expect(page.locator('[data-today-widget="games"]')).toBeVisible();await page.locator('[data-today-widget="games"]').scrollIntoViewIfNeeded();await expect(page.getByTestId('today-games')).toBeVisible()}
 if(!home)await expect(page.locator('.game-match')).toHaveCount(2);
 await expect.poll(()=>state.active).toBe(0);
 return {state,mock};
}
async function visibility(page,value){await page.evaluate(value=>{window.gamesTestVisibility=value;Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.gamesTestVisibility});document.dispatchEvent(new Event('visibilitychange'))},value)}

test('slow polling/focus coalesce without resetting draft, selected match or fleet preview',async({page})=>{
 await page.clock.install();const {state}=await boot(page);await page.getByLabel('Aufgaben-Einsatz',{exact:true}).selectOption('new');await page.getByLabel('Neue Aufgabe',{exact:true}).fill('Entwurf behalten');await page.locator('.game-match-head').filter({hasText:'Schiffe versenken'}).click();const fleet=await page.locator('.sea-cell.ship').evaluateAll(rows=>rows.map(row=>row.getAttribute('aria-label')));const taskReads=state.taskReads,baseline=state.reads;
 let release;state.gates.push(new Promise(resolve=>release=resolve));await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect.poll(()=>state.active).toBe(1);await page.clock.runFor(12000);await page.evaluate(()=>{window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('focus'))});expect(state.reads).toBe(baseline+1);expect(state.maxActive).toBe(1);await expect(page.getByLabel('Neue Aufgabe',{exact:true})).toHaveValue('Entwurf behalten');expect(await page.locator('.sea-cell.ship').evaluateAll(rows=>rows.map(row=>row.getAttribute('aria-label')))).toEqual(fleet);release();await expect.poll(()=>state.active).toBe(0);expect(state.taskReads).toBe(taskReads);await expect(page.locator('.game-match.selected')).toContainText('Schiffe versenken');
});

test('hidden tabs stop polling and focus while hidden; returning refreshes immediately',async({page})=>{
 await page.clock.install();const {state}=await boot(page);const baseline=state.reads;await visibility(page,'hidden');state.matches[0].rps.current_round=2;state.matches[0].rps.rounds.push({number:2,submitted_by_me:false,resolved:false});await page.clock.runFor(12000);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));expect(state.reads).toBe(baseline);await visibility(page,'visible');await expect(page.getByText('Runde 2 / 3',{exact:true})).toBeVisible();expect(state.reads).toBeGreaterThan(baseline);
});

test('a read started before a mutation cannot restore the old submitted state',async({page})=>{
 const {state}=await boot(page);let releaseRead,releaseCatchup;state.gates.push(new Promise(resolve=>releaseRead=resolve));await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect.poll(()=>state.active).toBe(1);await page.getByRole('button',{name:'Stein',exact:true}).click();await expect(page.getByText('Auswahl abgegeben – wartet auf die andere Person.')).toBeVisible();state.gates.push(new Promise(resolve=>releaseCatchup=resolve));const baseline=state.reads;releaseRead();await expect.poll(()=>state.reads).toBeGreaterThan(baseline);await expect(page.getByRole('button',{name:'Stein',exact:true})).toHaveCount(0);await expect(page.getByText('Auswahl abgegeben – wartet auf die andere Person.')).toBeVisible();releaseCatchup();expect(state.writes).toHaveLength(1);
});

test('Today retains confirmed rows on transient failure and removes them on denied retry',async({page})=>{
 const {state}=await boot(page,{home:true});const widget=page.getByTestId('today-games');await expect(widget).toContainText('Sam');state.errors=503;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(widget.getByRole('alert')).toContainText('Der letzte bestätigte Stand bleibt sichtbar.');await expect(widget).toContainText('Sam');state.errors=403;await widget.getByRole('button',{name:'Erneut laden',exact:true}).click();await expect(widget.getByRole('alert')).toContainText('Diese Spiele sind nicht mehr verfügbar.');await expect(widget).not.toContainText('Sam');await expect(widget.getByRole('button',{name:/Schere/})).toHaveCount(0);
});

test('widget retry and delayed results cannot restore a previous family',async({page})=>{
 const {state}=await boot(page,{home:true,multipleFamilies:true});const widget=page.getByTestId('today-games');state.errors=503;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(widget.getByRole('alert')).toBeVisible();state.errors=0;let release;state.gates.push(new Promise(resolve=>release=resolve));await widget.getByRole('button',{name:'Erneut laden',exact:true}).click();await expect.poll(()=>state.active).toBe(1);await page.locator('.family-switcher select').selectOption('family-2');await expect(page.locator('.family-switcher select')).toHaveValue('family-2');await expect(page.getByTestId('today-games').getByText('Keine offenen Spiele',{exact:true})).toBeVisible();release();await expect.poll(()=>state.active).toBe(0);await expect(page.getByTestId('today-games')).not.toContainText('Sam');
});

test('auth false discards a delayed game mutation, while true refresh preserves a valid draft',async({page})=>{
 const {state}=await boot(page);await page.getByLabel('Aufgaben-Einsatz',{exact:true}).selectOption('new');await page.getByLabel('Neue Aufgabe',{exact:true}).fill('Gültiger Entwurf');await page.evaluate(()=>window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:true}})));await expect(page.getByLabel('Neue Aufgabe',{exact:true})).toHaveValue('Gültiger Entwurf');let release,requested=false;await page.route('**/api/games/game-rps/rps/choice/',async route=>{requested=true;await new Promise(resolve=>release=resolve);return route.fulfill({json:match()})});await page.getByRole('button',{name:'Stein',exact:true}).click();await expect.poll(()=>requested).toBe(true);await page.evaluate(()=>{localStorage.removeItem('famuhle-session');window.dispatchEvent(new CustomEvent('famuhle:auth-changed',{detail:{authenticated:false}}))});await expect(page.locator('.game-match')).toHaveCount(0);release();await expect(page.locator('.game-match')).toHaveCount(0);await expect(page.getByText('Gültiger Entwurf',{exact:true})).toHaveCount(0);
});

test('a pending task-backed challenge locks its confirmed fields and retains the created task on retry',async({page})=>{
 const {state}=await boot(page);let release,taskBody,gameBody,gameWrites=0,taskWrites=0;
 await page.route('**/api/tasks/',async route=>{taskWrites+=1;taskBody=route.request().postDataJSON();await new Promise(resolve=>release=resolve);return route.fulfill({json:{id:'task-created',family:'family-1',title:taskBody.title,completed_at:null}})});
 await page.route('**/api/games/',route=>{if(route.request().method()==='GET')return route.fallback();gameWrites+=1;gameBody=route.request().postDataJSON();return gameWrites===1?route.fulfill({status:503,json:{detail:'temporary failure'}}):route.fulfill({json:match('game-created')})});
 await page.getByLabel('Aufgaben-Einsatz',{exact:true}).selectOption('new');await page.getByLabel('Neue Aufgabe',{exact:true}).fill('Bestätigte Aufgabe');await page.getByRole('checkbox',{name:'Ich bestätige Aufgabe, Gegner, Spiel und Einsatzregel verbindlich.',exact:true}).check();await page.getByRole('button',{name:'Aufgabe & Duell bestätigen',exact:true}).click();await expect.poll(()=>Boolean(taskBody)).toBe(true);
 await expect(page.getByLabel('Neue Aufgabe',{exact:true})).toBeDisabled();await expect(page.getByLabel('Gegner',{exact:true})).toBeDisabled();await expect(page.getByLabel('Einsatzregel',{exact:true})).toBeDisabled();expect(taskBody).toEqual({family:'family-1',title:'Bestätigte Aufgabe'});release();await expect(page.getByRole('alert')).toContainText('Aktion fehlgeschlagen. Bitte erneut versuchen.');await expect(page.getByLabel('Aufgabe',{exact:true})).toHaveValue('task-created');expect(gameBody.task_assignment).toEqual({task:'task-created',rule:'loser',confirmed:true});await page.getByRole('button',{name:'Aufgabe & Duell bestätigen',exact:true}).click();await expect(page).toHaveURL(/game=game-created/);expect(gameWrites).toBe(2);expect(taskWrites).toBe(1);expect(state.writes).toHaveLength(0);
});

test('an explicitly hidden Games row and saved order are never reset by live defaults',async({page})=>{
 const {state,mock}=await boot(page,{home:true,hiddenGames:true});const saved=clone(mock.todayLayout);await expect(page.locator('[data-today-widget="games"]')).toHaveCount(0);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));expect(state.reads).toBe(0);expect(mock.todayLayout).toEqual(saved);expect(state.layoutWrites).toEqual([]);await page.reload();await expect(page.locator('[data-today-widget="games"]')).toHaveCount(0);expect(mock.todayLayout.widgets.find(row=>row.id==='games').visible).toBe(false);expect(state.layoutWrites).toEqual([]);
});

for(const [language,title,round] of [['de','Spiele','Runde'],['en','Games','Round'],['fr','Jeux','Manche'],['nl','Spellen','Ronde'],['th','เกม','รอบ']])test(`Today game status supports ${language} with accessible links and no secret projection`,async({page})=>{
 await page.setViewportSize({width:390,height:844});await boot(page,{home:true,language});const widget=page.getByTestId('today-games');await expect(widget.getByRole('heading',{name:title,exact:true})).toBeVisible();await expect(widget).toContainText(`${round} 1 / 3`);await expect(widget.locator('.sea-grid')).toHaveCount(0);for(const width of [320,390]){await page.setViewportSize({width,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)}await page.evaluate(()=>document.documentElement.style.zoom='2');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.evaluate(()=>document.documentElement.style.zoom='1');const game=widget.getByRole('button',{name:new RegExp(`${round} 1 / 3`)});expect((await game.boundingBox()).height).toBeGreaterThanOrEqual(44);await game.focus();await page.keyboard.press('Enter');await expect(page).toHaveURL(/page=games.*game=game-rps/);
});
