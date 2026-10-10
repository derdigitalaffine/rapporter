import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const FIXED_NOW='2026-10-10T12:00:00.000Z';

async function freezeToday(page){
 await page.addInitScript(now=>{const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[now]))}static now(){return new RealDate(now).getTime()} }},FIXED_NOW);
}
async function mockTrips(page,rows){
 await page.route('**/api/trips/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(rows)}));
}

const trip=(id,title,starts_on,ends_on,extra={})=>({id,family:'family-1',title,destination:'Berlin',starts_on,ends_on,notes:'',archived:false,photos:[],...extra});

test('Today shows the next trip with civil-date countdown and opens trips',async({page})=>{
 await freezeToday(page);await installApiMocks(page,{dismissOnboarding:true});
 await mockTrips(page,[
  trip('later','Sommerferien','2026-10-20','2026-10-25'),
  trip('next','Herbstferien','2026-10-13','2026-10-17'),
 ]);
 await page.goto('/');
 const banner=page.getByTestId('today-trip-banner');
 await expect(banner).toBeVisible();
 await expect(banner).toContainText('Nächste Reise');
 await expect(banner).toContainText('Herbstferien');
 await expect(banner).toContainText('Berlin');
 await expect(banner).toContainText('Noch 3 Tage');
 await banner.click();
 await expect(page).toHaveURL(/page=trips/);
 await expect(page.getByRole('heading',{name:'Reisen',exact:true})).toBeVisible();
});

test('active trip wins over future trips and uses the in-trip countdown',async({page})=>{
 await freezeToday(page);await installApiMocks(page,{dismissOnboarding:true});
 await mockTrips(page,[
  trip('future','Nächste Woche','2026-10-11','2026-10-15'),
  trip('active','Kurzurlaub','2026-10-09','2026-10-12',{destination:'Pfalz'}),
 ]);
 await page.goto('/');
 const banner=page.getByTestId('today-trip-banner');
 await expect(banner).toContainText('Kurzurlaub');
 await expect(banner).toContainText('Pfalz');
 await expect(banner).toContainText('Tag 2 von 4');
 await expect(banner).not.toContainText('Nächste Woche');
});

test('finished and archived trips do not create a dashboard banner',async({page})=>{
 await freezeToday(page);await installApiMocks(page,{dismissOnboarding:true});
 await mockTrips(page,[
  trip('finished','Vergangene Reise','2026-10-01','2026-10-05'),
  trip('archived','Archivierte Reise','2026-10-12','2026-10-14',{archived:true}),
 ]);
 await page.goto('/');
 await expect(page.getByTestId('today-trip-banner')).toHaveCount(0);
});

test('trip banner stays narrow without horizontal overflow on phone',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await freezeToday(page);await installApiMocks(page,{dismissOnboarding:true});
 await mockTrips(page,[trip('long','Sehr langer Familienurlaub mit einem bewusst langen Namen','2026-10-13','2026-10-20',{destination:'Ein ebenfalls sehr langes Reiseziel für den mobilen Layouttest'})]);
 await page.goto('/');
 await expect(page.getByTestId('today-trip-banner')).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflow).toBeLessThanOrEqual(0);
});

test('trip banner follows the English locale',async({page})=>{
 await freezeToday(page);await installApiMocks(page,{language:'en',dismissOnboarding:true});
 await mockTrips(page,[trip('next','Autumn break','2026-10-13','2026-10-17',{destination:'London'})]);
 await page.goto('/');
 const banner=page.getByTestId('today-trip-banner');
 await expect(banner).toContainText('Next trip');
 await expect(banner).toContainText('3 days to go');
});
