import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {authenticate,installMockApi} from './mock-api.js';

async function openAuthenticated(page,path='/',language='de',options={}){
  await installMockApi(page,options);
  await authenticate(page,language);
  await page.goto(path);
  await expect(page.locator('.app-shell')).toBeVisible();
}

async function expectNoCriticalA11y(page){
  const results=await new AxeBuilder({page}).analyze();
  const critical=results.violations.filter(v=>v.impact==='critical');
  expect(critical,critical.map(v=>`${v.id}: ${v.help}`).join('\n')).toEqual([]);
}

async function expectNoHorizontalOverflow(page){
  const overflow=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,width:window.innerWidth}));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width+1);
}

test('login → Today → add and complete a task',async({page})=>{
  await installMockApi(page);
  await page.goto('/');
  await page.getByLabel('Benutzername').fill('mama');
  await page.getByLabel('Passwort').fill('secret');
  await page.getByRole('button',{name:'Anmelden'}).click();
  await expect(page.getByText('Hallo Familie 👋')).toBeVisible();
  await page.locator('.bottom-nav').getByRole('button',{name:'Aufgaben'}).click();
  const quick=page.getByPlaceholder('Aufgabe suchen oder hinzufügen …');
  await quick.fill('Spülmaschine ausräumen');
  await page.locator('.smart-input').getByRole('button',{name:'Hinzufügen'}).click();
  const row=page.locator('.smart-row').filter({hasText:'Spülmaschine ausräumen'});
  await expect(row).toBeVisible();
  await row.getByRole('button',{name:'Erledigen'}).click();
  await expect(page.locator('.smart-row').filter({hasText:'Spülmaschine ausräumen'})).toHaveCount(0);
});

test('shopping item can be added, edited and checked',async({page})=>{
  await openAuthenticated(page,'/?page=shopping');
  await page.getByPlaceholder('Artikel suchen oder hinzufügen …').fill('Äpfel');
  await page.locator('.smart-input').getByRole('button',{name:'Hinzufügen'}).click();
  let row=page.locator('.shopping-row').filter({hasText:'Äpfel'});
  await expect(row).toBeVisible();
  await row.locator('.row-main-button').click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Artikel').fill('Bio-Äpfel');
  await dialog.getByRole('button',{name:'Speichern'}).click();
  row=page.locator('.shopping-row').filter({hasText:'Bio-Äpfel'});
  await expect(row).toBeVisible();
  await row.getByRole('button',{name:/Bio-Äpfel.*Erledigen/}).click();
  await expect(page.locator('.done-items')).toContainText('Bio-Äpfel');
});

test('calendar event create, edit and delete flow',async({page})=>{
  await openAuthenticated(page,'/?page=calendar');
  await page.getByRole('button',{name:'Termin hinzufügen'}).click();
  let dialog=page.getByRole('dialog');
  await dialog.getByLabel('Titel').fill('Zahnarzt');
  await dialog.getByRole('button',{name:'Speichern'}).click();
  let event=page.locator('.agenda-event').filter({hasText:'Zahnarzt'});
  await expect(event).toBeVisible();
  await event.click();
  await page.getByRole('dialog').getByRole('button',{name:'Termin bearbeiten'}).click();
  dialog=page.getByRole('dialog');
  await dialog.getByLabel('Titel').fill('Zahnarzt Kind');
  await dialog.getByRole('button',{name:'Speichern'}).click();
  event=page.locator('.agenda-event').filter({hasText:'Zahnarzt Kind'});
  await expect(event).toBeVisible();
  await event.click();
  await page.getByRole('dialog').getByRole('button',{name:'Termin bearbeiten'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Termin löschen'}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'Termin löschen'}).click();
  await expect(page.locator('.agenda-event').filter({hasText:'Zahnarzt Kind'})).toHaveCount(0);
});

test('member invitation reaches share-ready state',async({page})=>{
  await openAuthenticated(page,'/?page=members');
  await page.getByRole('button',{name:'Person einladen'}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Anzeigename').fill('Oma');
  await dialog.getByRole('button',{name:/Weiter zur Rolle/}).click();
  await dialog.getByRole('button',{name:'Einladung erstellen'}).click();
  await expect(dialog.getByRole('heading',{name:'Einladung bereit'})).toBeVisible();
  await expect(dialog).toContainText('Oma');
});

test('automation builder saves a rule',async({page})=>{
  await openAuthenticated(page,'/?page=automations');
  await page.locator('.builder-choice').filter({hasText:'Müllabfuhr ist morgen'}).click();
  await page.getByRole('button',{name:/Weiter zur Aktion/}).click();
  await page.locator('.builder-choice').filter({hasText:'Aufgabe anlegen'}).click();
  await page.getByRole('button',{name:/Regel speichern/}).click();
  await expect(page.getByText('Regel gespeichert.')).toBeVisible();
});

test('dialog traps focus, closes with Escape and restores trigger focus',async({page})=>{
  await openAuthenticated(page,'/?page=tasks');
  const trigger=page.locator('.smart-row').filter({hasText:'Müll rausbringen'}).locator('.row-main-button');
  await trigger.click();
  const dialog=page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(()=>document.querySelector('[role="dialog"]')?.contains(document.activeElement))).toBeTruthy();
  await page.keyboard.press('Tab');
  expect(await page.evaluate(()=>document.querySelector('[role="dialog"]')?.contains(document.activeElement))).toBeTruthy();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('integration hub renders deterministic error state',async({page})=>{
  await openAuthenticated(page,'/?page=integrations','de',{integrationMode:'error'});
  await expect(page.getByText('Quelle nicht erreichbar')).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('English locale stays English in core flows',async({page})=>{
  await openAuthenticated(page,'/?page=tasks','en');
  await expect(page.getByRole('heading',{name:'Tasks'})).toBeVisible();
  await expect(page.getByPlaceholder('Search or add task …')).toBeVisible();
  await expect(page.getByText('Familienaufgaben')).toHaveCount(0);
  await page.goto('/?page=automations');
  await expect(page.getByRole('heading',{name:'If → Then'})).toBeVisible();
  await expect(page.getByText('Eigene Regel')).toHaveCount(0);
});

test('critical accessibility, overflow and visual capture',async({page},testInfo)=>{
  await openAuthenticated(page,'/');
  await expectNoCriticalA11y(page);
  await expectNoHorizontalOverflow(page);
  const screenshotPath=testInfo.outputPath(`today-${testInfo.project.name}.png`);
  await page.screenshot({path:screenshotPath,fullPage:true,animations:'disabled'});
  await testInfo.attach(`today-${testInfo.project.name}`,{path:screenshotPath,contentType:'image/png'});
  await page.goto('/?page=tasks');
  await expectNoCriticalA11y(page);
  await expectNoHorizontalOverflow(page);
});

test('service worker can register and update without a white screen',async({browser})=>{
  const context=await browser.newContext({serviceWorkers:'allow',viewport:{width:390,height:844}});
  const page=await context.newPage();
  await page.goto('http://127.0.0.1:4173/');
  await expect(page.getByRole('heading',{name:'Anmelden'})).toBeVisible();
  const result=await page.evaluate(async()=>{
    if(!('serviceWorker'in navigator))return {supported:false};
    const registration=await Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error('service-worker-timeout')),10000))]);
    await registration.update();
    return {supported:true,script:registration.active?.scriptURL||registration.installing?.scriptURL||''};
  });
  expect(result.supported).toBeTruthy();
  expect(result.script).toContain('/sw.js');
  await expect(page.locator('#root')).not.toBeEmpty();
  await expect(page.getByText('fam-uh-le')).toBeVisible();
  await context.close();
});
