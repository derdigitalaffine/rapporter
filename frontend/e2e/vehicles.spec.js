import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api';

async function setup(page,{denied=false,gpsDenied=false,language='de',active=false,mapConfigured=false}={}){
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
  if(path==='/api/vehicles/map-config/')return json(mapConfigured?{configured:true,tile_url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png'}:{configured:false});
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

const OSM_TEST_TILE='iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAAADIElEQVR4nO3UIQEAIADAMKB/UwwNIAbiW4Krz332HUDS+h0A/GMAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEGYAEPYA2ysFxQM+KpAAAAAASUVORK5CYII=';

// Real renderer/worker under the production policies; OSM requests are mocked, never sent live.
test('OSM map renders with self worker, origin referer, cache and no credentials under CSP',async({page,context})=>{
 await setup(page,{active:true,mapConfigured:true});
 await context.addCookies([{name:'private_auth',value:'must-not-leave',domain:'tile.openstreetmap.org',path:'/',secure:true,sameSite:'None'}]);
 await page.addInitScript(()=>{
  window.__osmRequests=[];window.__mapWorkers=[];window.__cspViolations=[];
  const originalFetch=window.fetch.bind(window);
  window.fetch=(input,init)=>{const request=new Request(input,init);if(request.url.startsWith('https://tile.openstreetmap.org/'))window.__osmRequests.push({url:request.url,credentials:request.credentials,cache:request.cache,referrerPolicy:request.referrerPolicy});return originalFetch(input,init)};
  const NativeWorker=window.Worker;
  window.Worker=class extends NativeWorker{constructor(url,options){super(url,options);window.__mapWorkers.push(new URL(url,location.href).href)}};
  document.addEventListener('securitypolicyviolation',event=>window.__cspViolations.push({directive:event.effectiveDirective,url:event.blockedURI}));
 });
 const {readFile}=await import('node:fs/promises');
 const caddy=await readFile(new URL('../../Caddyfile',import.meta.url),'utf8');
 const csp=caddy.match(/Content-Security-Policy "([^"]+)"/)[1];
 const permissions=caddy.match(/Permissions-Policy "([^"]+)"/)[1];
 await page.route('http://127.0.0.1:4173/**',async route=>{
  if(route.request().resourceType()!=='document')return route.fallback();
  const response=await route.fetch();
  return route.fulfill({response,headers:{...response.headers(),'Content-Security-Policy':csp,'Permissions-Policy':permissions,'Referrer-Policy':'same-origin'}});
 });
 const tileRequests=[];
 await page.route('https://tile.openstreetmap.org/**',async route=>{
  tileRequests.push({url:route.request().url(),headers:await route.request().allHeaders()});
  return route.fulfill({contentType:'image/png',body:Buffer.from(OSM_TEST_TILE,'base64'),headers:{'Access-Control-Allow-Origin':'*','Cache-Control':'public, max-age=604800'}});
 });
 await open(page);
 expect(tileRequests).toHaveLength(0);
 await page.getByRole('button',{name:'Karte anzeigen',exact:true}).click();
 await expect(page.locator('.vehicle-map canvas')).toBeVisible();
 await expect(page.locator('.maplibregl-ctrl-attrib a[href="https://www.openstreetmap.org/copyright"]')).toBeVisible();
 await expect.poll(()=>tileRequests.length).toBeGreaterThan(0);
 await expect(page.getByText('Karte wird geladen …')).toHaveCount(0);
 await expect(page.getByText('Kartenbasis nicht erreichbar. Fahrtenbuch bleibt verfügbar.')).toHaveCount(0);
 const requests=await page.evaluate(()=>window.__osmRequests);
 expect(requests.length).toBeGreaterThan(0);
 for(const request of requests){expect(request.credentials).toBe('omit');expect(request.cache).toBe('default');expect(request.referrerPolicy).toBe('origin');expect(request.url).not.toMatch(/family|vehicle|journey|key=/)}
 for(const request of tileRequests){expect(request.headers.cookie).toBeUndefined();expect(request.headers.referer).toBe('http://127.0.0.1:4173/')}
 const workers=await page.evaluate(()=>window.__mapWorkers);
 expect(workers.length).toBeGreaterThan(0);
 for(const worker of workers)expect(worker).toMatch(/^http:\/\/127\.0\.0\.1:4173\/assets\//);
 expect(await page.evaluate(()=>window.__cspViolations)).toEqual([]);
});

test('all deployment variants allow only first-party GPS and targeted OSM resources',async()=>{
 const {readFile}=await import('node:fs/promises');
 for(const filename of ['Caddyfile','Caddyfile.proxy','Caddyfile.selfsigned']){
  const text=await readFile(new URL(`../../${filename}`,import.meta.url),'utf8');
  expect(text).toContain('Permissions-Policy "camera=(), microphone=(self), geolocation=(self)"');
  expect(text).toContain("media-src 'self' blob:");
  expect(text).toContain("connect-src 'self' https://tile.openstreetmap.org;");
  expect(text).toContain("worker-src 'self';");
  expect(text).toContain('Referrer-Policy same-origin');
  expect(text).not.toContain('geofabrik');
 }
});
