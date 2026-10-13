import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api';

async function setup(page,{denied=false,gpsDenied=false,language='de',active=false}={}){
 await installApiMocks(page,{language});
 const car={id:'car-1',family:'family-1',name:'Familienauto',plate:'B-OS 2026',manufacturer:'VW',model:'Golf',fuel_type:'petrol',odometer:'100.0',vin:'',first_registration:null,notes:'',archived:false};
 const state={cars:[car],fuel:[],journeys:[],points:[],active:null,failFuel:0,failPoints:0,tokens:[]};
 const trip=()=>({id:'trip-1',vehicle:'car-1',started_at:new Date(Date.now()-1000).toISOString(),ended_at:null,start_odometer:'100.0',end_odometer:null,purpose:'',kind:'private',distance_m:0,point_count:0});
 if(active){state.active=trip();state.journeys=[state.active]}
 await page.addInitScript(({gpsDenied})=>{window.__gpsWatch=null;window.__gpsCleared=0;Object.defineProperty(navigator,'geolocation',{value:{watchPosition(success,error){window.__gpsWatch=success;if(gpsDenied)setTimeout(()=>error({code:1}),0);return 7},clearWatch(){window.__gpsWatch=null;window.__gpsCleared++}}})},{gpsDenied});
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  const json=(payload,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(payload)});
  if(path==='/api/entitlements/')return json({tier:'premium',display_name:'Premium',capabilities:['vehicles','travel','pets','pregnancy_baby']});
  if(!path.startsWith('/api/vehicles/')&&!path.startsWith('/api/vehicle-journeys/'))return route.fallback();
  if(denied)return json({detail:'forbidden'},403);
  if(path==='/api/vehicles/'&&method==='GET')return json(state.cars);
  if(path==='/api/vehicles/'&&method==='POST'){const created={...car,...body,id:'car-2'};state.cars.push(created);return json(created,201)}
  if(path==='/api/vehicles/car-1/'&&method==='PATCH'){Object.assign(car,body);return json(car)}
  if(path==='/api/vehicles/active/')return json(state.active);
  if(path==='/api/vehicles/map-config/')return json({configured:false});
  if(path==='/api/vehicles/car-1/fuel/'&&method==='GET')return json(state.fuel);
  if(path==='/api/vehicles/car-1/fuel/'&&method==='POST'){state.tokens.push(body.request_id);if(state.failFuel-->0)return json({detail:'failed'},500);const entry={...body,id:'fuel-1',vehicle:'car-1'};state.fuel=[entry];return json(entry,201)}
  if(path==='/api/vehicles/car-1/journeys/'&&method==='GET')return json(state.journeys);
  if(path==='/api/vehicles/car-1/journeys/'&&method==='POST'){state.active={...trip(),...body};state.journeys=[state.active];return json(state.active,201)}
  if(path==='/api/vehicle-journeys/trip-1/points/'){if(state.failPoints-->0)return json({detail:'failed'},500);for(const p of body.points)if(!state.points.some(existing=>existing.sequence===p.sequence))state.points.push(p);state.active.point_count=state.points.length;state.active.distance_m=42;return json(state.active)}
  if(path==='/api/vehicle-journeys/trip-1/'&&method==='GET')return json({...state.journeys[0],points:state.points});
  if(path==='/api/vehicle-journeys/trip-1/'&&method==='POST'){Object.assign(state.active,{ended_at:new Date().toISOString(),end_odometer:body.end_odometer});const finished=state.active;state.active=null;car.odometer=String(body.end_odometer);return json(finished)}
  if(path==='/api/vehicle-journeys/trip-1/'&&method==='DELETE'){state.journeys=[];state.points=[];return route.fulfill({status:204,body:''})}
  return json([]);
 });
 return state;
}
async function open(page){await page.goto('/?page=vehicles');await expect(page.getByRole('heading',{name:'Familienauto',exact:true})).toBeVisible()}
async function start(page){await page.getByRole('checkbox',{name:'Ich möchte für diese Fahrt meinen Standort aufzeichnen.'}).check();await page.getByRole('button',{name:'Fahrt starten',exact:true}).click();await expect(page.getByText('GPS wird aufgezeichnet')).toBeVisible()}
async function emit(page){await page.evaluate(()=>window.__gpsWatch?.({coords:{latitude:52.5,longitude:13.4,accuracy:5},timestamp:Date.now()}))}

test('fuel editor preserves inputs and retries a stable token',async({page})=>{
 const state=await setup(page);await open(page);state.failFuel=1;await page.getByRole('button',{name:'Tankvorgang erfassen'}).click();await page.getByRole('spinbutton',{name:'Menge',exact:true}).fill('40');await page.getByRole('spinbutton',{name:'Gesamtbetrag',exact:true}).fill('65.50');await page.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();await expect(page.getByRole('spinbutton',{name:'Menge',exact:true})).toHaveValue('40');await page.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.getByText(/40 l/)).toBeVisible();expect(state.tokens[0]).toBe(state.tokens[1]);
});

test('consent, GPS batch, pause and stop save one journey',async({page})=>{
 const state=await setup(page);await open(page);await expect(page.getByRole('button',{name:'Fahrt starten',exact:true})).toBeDisabled();await start(page);await emit(page);await expect(page.getByText('1 GPS-Punkte warten auf Übertragung')).toBeVisible();await page.getByRole('button',{name:'GPS pausieren'}).click();expect(await page.evaluate(()=>window.__gpsWatch)).toBeNull();await page.getByLabel('Kilometerstand bei Ende (km)').fill('110');await page.getByRole('button',{name:'Fahrt beenden',exact:true}).click();await expect(page.getByRole('button',{name:'Fahrt starten',exact:true})).toBeVisible();expect(state.points).toHaveLength(1);expect(state.journeys[0].end_odometer).toBe('110');await expect(page.getByText(/Beendet/)).toBeVisible();
});

test('GPS denied leaves an open journey that can still be finished',async({page})=>{
 await setup(page,{gpsDenied:true});await open(page);await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Fahrt starten',exact:true}).click();await expect(page.getByText(/Standort nicht verfügbar/)).toBeVisible();await page.getByLabel('Kilometerstand bei Ende (km)').fill('100');await page.getByRole('button',{name:'Fahrt beenden',exact:true}).click();await expect(page.getByRole('button',{name:'Fahrt starten',exact:true})).toBeVisible();
});

test('reload keeps pending GPS and never silently resumes tracking',async({page})=>{
 const state=await setup(page);await open(page);await start(page);await emit(page);await expect(page.getByText('1 GPS-Punkte warten auf Übertragung')).toBeVisible();await page.reload();await expect(page.getByText('GPS pausiert – Fahrt bleibt offen')).toBeVisible();expect(await page.evaluate(()=>window.__gpsWatch)).toBeNull();await expect(page.getByText('1 GPS-Punkte warten auf Übertragung')).toBeVisible();await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Aufzeichnung fortsetzen'}).click();await expect(page.getByText('GPS wird aufgezeichnet')).toBeVisible();expect(state.points).toHaveLength(1);
});

test('failed GPS sync does not close journey or lose pending points',async({page})=>{
 const state=await setup(page);await open(page);await start(page);await emit(page);await expect(page.getByText('1 GPS-Punkte warten auf Übertragung')).toBeVisible();state.failPoints=1;await page.getByLabel('Kilometerstand bei Ende (km)').fill('105');await page.getByRole('button',{name:'Fahrt beenden',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();expect(state.active).not.toBeNull();await expect(page.getByText('1 GPS-Punkte warten auf Übertragung')).toBeVisible();await page.getByRole('button',{name:'Fahrt beenden',exact:true}).click();await expect(page.getByRole('button',{name:'Fahrt starten',exact:true})).toBeVisible();expect(state.active).toBeNull();expect(state.points).toHaveLength(1);
});

test('navigation stops GPS and expiry clears local routes',async({page})=>{
 await setup(page);await open(page);await start(page);await emit(page);await expect(page.getByText('1 GPS-Punkte warten auf Übertragung')).toBeVisible();await page.locator('.bottom-nav').getByRole('button',{name:'Mehr',exact:true}).click();await expect(page.getByRole('heading',{name:'Mehr',exact:true})).toBeVisible();expect(await page.evaluate(()=>window.__gpsWatch)).toBeNull();await page.evaluate(()=>window.dispatchEvent(new CustomEvent('famuhle:session-expired')));expect(await page.evaluate(()=>Object.keys(sessionStorage).filter(key=>key.startsWith('vehicle-gps:')))).toEqual([]);
});

test('unauthorized deep links expose no vehicle or start controls',async({page})=>{
 await setup(page,{denied:true});await page.goto('/?page=vehicles');await expect(page.getByText(/Dieses Premiummodul/)).toBeVisible();await expect(page.getByRole('button',{name:'Fahrzeug hinzufügen',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Fahrt starten',exact:true})).toHaveCount(0);
});

test('vehicle editor, mobile zoom and accessibility remain usable',async({page})=>{
 await setup(page);await open(page);await page.setViewportSize({width:320,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.getByRole('button',{name:'Stammdaten bearbeiten'}).click();await page.getByRole('textbox',{name:'Name',exact:true}).fill('Unser Golf');await page.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.getByRole('heading',{name:'Unser Golf'})).toBeVisible();await page.getByRole('button',{name:'Stammdaten bearbeiten'}).click();await page.getByRole('textbox',{name:'Name',exact:true}).focus();await page.keyboard.press('Shift+Tab');await expect(page.getByRole('button',{name:'Abbrechen',exact:true}).first()).toBeFocused();await page.keyboard.press('Escape');await page.emulateMedia({reducedMotion:'reduce'});await page.locator('main').evaluate(el=>el.style.zoom='2');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.locator('main').evaluate(el=>el.style.zoom='1');const result=await new AxeBuilder({page}).include('.vehicles-hub').analyze();expect(result.violations).toEqual([]);
});

test('English flow and CSV export are available',async({page})=>{
 await setup(page,{language:'en',active:true});await page.goto('/?page=vehicles');await expect(page.getByRole('heading',{name:'Vehicles and logbook'})).toBeVisible();await expect(page.getByText('GPS paused – journey remains open')).toBeVisible();await page.getByLabel('Ending odometer (km)').fill('101');await page.getByRole('button',{name:'Finish journey',exact:true}).click();const download=page.waitForEvent('download');await page.getByRole('button',{name:'Export logbook as CSV'}).click();expect((await download).suggestedFilename()).toBe('fahrtenbuch.csv');
});


test('CSV safely escapes spreadsheet formulas without exporting GPS',async()=>{const {logbookCsv}=await import('../src/vehicle-tracking.js');const csv=logbookCsv([{started_at:'2026-10-13',ended_at:'2026-10-13',kind:'private',purpose:'=HYPERLINK(\"https://example.com\")',start_odometer:100,end_odometer:101,distance_m:1000}]);expect(csv).toContain("'=HYPERLINK");expect(csv).not.toContain('latitude');expect(csv).toContain('1.0')});
