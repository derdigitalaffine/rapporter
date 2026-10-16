import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api';

test.use({serviceWorkers:'block'});
const chunkPattern=/\/assets\/(?:TravelHub|LoyaltyCards|NotesHub|VehiclesHub|SettingsHub|StatisticsHub)-[^/]+\.js$/;
test('rare feature chunks are absent at Today and load on navigation/reload/back',async({page})=>{
  await installApiMocks(page);
  const chunks=[];page.on('request',request=>{if(chunkPattern.test(new URL(request.url()).pathname))chunks.push(new URL(request.url()).pathname);});
  await page.goto('/');await expect(page.locator('.bottom-nav')).toBeVisible();
  expect(chunks).toEqual([]);
  await page.locator('.bottom-nav').getByRole('button',{name:'Mehr',exact:true}).click();
  await page.getByRole('button',{name:'Reisen',exact:true}).click();
  await expect(page.locator('.travel-hub')).toBeVisible();
  expect(chunks.some(path=>path.includes('TravelHub-'))).toBe(true);
  await page.reload();await expect(page.locator('.travel-hub')).toBeVisible();
  await page.getByRole('button',{name:'Zurück',exact:true}).first().click();
  await expect(page.locator('main[data-page="more"] .menu-row').first()).toBeVisible();
});
for(const offline of [false,true])test(`chunk unavailable keeps shell usable (${offline?'offline':'network failure'})`,async({page},testInfo)=>{
  await installApiMocks(page);
  await page.route('**/assets/TravelHub-*.js',route=>route.abort('failed'));
  if(offline)await page.addInitScript(()=>Object.defineProperty(navigator,'onLine',{get:()=>false,configurable:true}));
  await page.goto('/?page=trips');
  await expect(page.getByRole('alert').filter({hasText:offline?'offline noch nicht verfügbar':'konnte nicht geladen'})).toBeVisible();
  await expect(page.locator('.topbar')).toBeVisible();
  await expect(page.getByRole('button',{name:'Erneut versuchen',exact:true})).toBeVisible();
  if(!offline)await expect(page.getByRole('button',{name:'Nach App-Update suchen'})).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
  await testInfo.attach('chunk-unavailable',{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
  await page.getByRole('button',{name:'Zurück',exact:true}).click();
  await expect(page.locator('main[data-page="more"] .menu-row').first()).toBeVisible();
});
test('known capability lock does not request the feature chunk',async({page})=>{
  await installApiMocks(page);
  await page.route('**/api/entitlements/**',route=>route.fulfill({json:{tier:'light',capabilities:['calendar','notes']}}));
  const chunks=[];page.on('request',request=>{if(chunkPattern.test(new URL(request.url()).pathname))chunks.push(request.url());});
  await page.goto('/?page=trips');
  await expect(page.getByText('Dieser Bereich ist in deinem Tarif nicht enthalten.',{exact:true})).toBeVisible();
  expect(chunks).toEqual([]);
});
test('transient chunk failure has a working retry path',async({page})=>{
  await installApiMocks(page);
  await page.route('**/assets/TravelHub-*.js',route=>route.abort('failed'));
  await page.goto('/?page=trips');
  await expect(page.getByRole('alert').filter({hasText:'konnte nicht geladen'})).toBeVisible();
  await page.unroute('**/assets/TravelHub-*.js');
  await page.getByRole('button',{name:'Erneut versuchen',exact:true}).click();
  await expect(page.locator('.travel-hub')).toBeVisible();
});
