import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const FIXED_NOW='2026-10-09T12:00:00.000Z';

async function bootVisual(page,path='/'){
  await page.addInitScript(now=>{const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[now]))}static now(){return new RealDate(now).getTime()} }},FIXED_NOW);
  const state=await installApiMocks(page,{dismissOnboarding:true});
  state.tasks[0].due_at='2026-10-09T15:00:00.000Z';
  state.events[0].starts_at='2026-10-08T10:00:00.000Z';state.events[0].ends_at='2026-10-08T11:00:00.000Z';
  state.events[1].starts_at='2026-10-09T17:00:00.000Z';state.events[1].ends_at='2026-10-09T18:00:00.000Z';
  state.integrations[0].next_sync_at='2026-10-09T13:00:00.000Z';
  await page.goto(path);await page.waitForLoadState('networkidle');await page.evaluate(()=>document.fonts.ready.then(()=>true));await expect(page.locator('.app-shell')).toBeVisible();return state;
}
async function snapshot(page,name){await expect(page).toHaveScreenshot(`${name}.png`,{animations:'disabled',caret:'hide',maxDiffPixels:name==='members'?300:100})}
async function bottom(page,label){await page.locator('.bottom-nav').getByRole('button',{name:new RegExp(`^${label}$`)}).click()}

test('visual · Today',async({page})=>{await bootVisual(page);await expect(page.getByRole('heading',{name:'Hallo Familie'})).toBeVisible();await snapshot(page,'today')});
test('visual · Tasks',async({page})=>{await bootVisual(page);await bottom(page,'Aufgaben');await expect(page.getByRole('heading',{name:'Aufgaben',exact:true})).toBeVisible();await snapshot(page,'tasks')});
test('visual · Shopping planning',async({page})=>{await bootVisual(page);await bottom(page,'Einkauf');await expect(page.getByText('Milch',{exact:true})).toBeVisible();await snapshot(page,'shopping-planning')});
test('visual · Shopping store mode',async({page})=>{await bootVisual(page);await bottom(page,'Einkauf');await page.getByRole('button',{name:/Im Laden/i}).click();await expect(page.locator('.shopping-page')).toHaveClass(/store-mode/);await snapshot(page,'shopping-store')});
test('visual · Calendar',async({page})=>{await bootVisual(page,'/?page=calendar');await expect(page.getByText('Kinderarzt',{exact:true})).toBeVisible();await snapshot(page,'calendar')});
test('visual · Members',async({page})=>{await bootVisual(page,'/?page=members');await expect(page.getByRole('button',{name:'Person einladen'})).toBeVisible();await snapshot(page,'members')});
test('visual · Integrations',async({page})=>{await bootVisual(page,'/?page=integrations');await expect(page.locator('.integration-health-card').filter({hasText:'Open-Meteo'})).toBeVisible();await snapshot(page,'integrations')});
test('visual · Automations',async({page})=>{await bootVisual(page,'/?page=automations');await expect(page.locator('.automation-template').first()).toBeVisible();await snapshot(page,'automations')});
test('visual · More',async({page})=>{await bootVisual(page);await bottom(page,'Mehr');await expect(page.getByRole('heading',{name:'Mehr',exact:true})).toBeVisible();const expenses=page.getByRole('button',{name:'Ausgabe',exact:true});await expect(expenses).toBeVisible();await expenses.evaluate(element=>{element.style.display='none'});await page.locator('main .menu-row').filter({hasText:'Mein Profil'}).evaluate(node=>node.remove());await snapshot(page,'more')});
test('visual · Task editor dialog',async({page})=>{await bootVisual(page);await bottom(page,'Aufgaben');await page.locator('.global-create-fab').click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Aufgabe hinzufügen'})).toBeVisible();await snapshot(page,'dialog-task-editor')});
test('visual · Event editor dialog',async({page})=>{await bootVisual(page,'/?page=calendar');await page.locator('.global-create-fab').click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Termin hinzufügen'})).toBeVisible();await snapshot(page,'dialog-event-editor')});
test('visual · Invite success dialog',async({page})=>{await bootVisual(page,'/?page=members');await page.getByRole('button',{name:'Person einladen'}).click();let dialog=page.getByRole('dialog');await dialog.getByLabel('Anzeigename').fill('Oma');await dialog.getByRole('button',{name:/Weiter zu Rolle/}).click();dialog=page.getByRole('dialog');await dialog.getByText('Gast',{exact:true}).first().click();await dialog.getByRole('button',{name:'Einladung erstellen'}).click();await expect(dialog.getByText('EINLADUNG ERSTELLT',{exact:true})).toBeVisible();await snapshot(page,'dialog-invite-success')});
