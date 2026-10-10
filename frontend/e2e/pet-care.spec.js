import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function installPetMocks(page,operations,{showNav=true}={}){
 const moduleState={key:'pet_care',enabled:true,authorized:true,can_manage:true,show_in_main_navigation:showNav,permissions:{can_care:true,health_manage:true}};
 const pets=[{id:'pet-1',family:'family-1',name:'Luna',species:'Hund',breed:'Labrador',sex:'female',quick_actions:[],active:true,microchip_id:'',insurance_provider:'',insurance_number:'',primary_vet_name:'Praxis',primary_vet_phone:'',allergies:'',important_notes:''},{id:'pet-2',family:'family-1',name:'Milo',species:'Katze',breed:'',sex:'male',quick_actions:[],active:true,microchip_id:'',insurance_provider:'',insurance_number:'',primary_vet_name:'',primary_vet_phone:'',allergies:'',important_notes:''}];
 const logs={'pet-1':[],'pet-2':[]};let next=1;
 await page.route('**/api/pets/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname.replace(/^\/api/,'');const method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  const ok=value=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  if(path==='/pets/module/')return ok(moduleState);
  if(path==='/pets/profiles/')return ok({pets});
  const care=path.match(/^\/pets\/(pet-[12])\/care\/$/);
  if(care){const id=care[1];if(method==='POST'){const row={id:`log-${next++}`,pet:id,...body,created_by:1,external_caregiver:''};logs[id].unshift(row);operations.push({method,path,body,row});return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify(row)})}const rows=logs[id];return ok({pet:pets.find(p=>p.id===id),summary:{counts:Object.fromEntries(['feed','water','walk','toilet','grooming','training'].map(k=>[k,rows.filter(r=>r.kind===k).length])),walk_minutes:0,medication_doses:0,observation_count:0,open_medications:[]},events:rows})}
  const detail=path.match(/^\/pets\/care\/(log-\d+)\/$/);if(detail&&method==='PATCH'){for(const id of Object.keys(logs)){const row=logs[id].find(r=>r.id===detail[1]);if(row){Object.assign(row,body);operations.push({method,path,body,row});return ok(row)}}return route.fulfill({status:404,body:'{}'})}
  if(path.match(/^\/pets\/pet-[12]\/health-events\/$/))return ok({events:[]});
  if(path.match(/^\/pets\/pet-[12]\/medications\/$/))return ok({medications:[]});
  if(path.match(/^\/pets\/pet-[12]\/weights\/$/))return ok({weights:[]});
  if(path.match(/^\/pets\/pet-[12]\/observations\/$/))return ok({observations:[]});
  if(path.match(/^\/pets\/pet-[12]\/vet-questions\/$/))return ok({questions:[]});
  if(path.match(/^\/pets\/pet-[12]\/documents\/$/))return ok({documents:[]});
  if(path.match(/^\/pets\/pet-[12]\/shares\/$/))return ok({shares:[]});
  if(path.match(/^\/pets\/pet-[12]\/handover\/$/))return ok({summary:{counts:{},walk_minutes:0,medication_doses:0,observation_count:0,open_medications:[]},notes:[]});
  return ok({});
 });
}

test('pet quick logs and walk timer stay attached to the selected pet',async({page})=>{
 const operations=[];await installApiMocks(page,{language:'de'});await installPetMocks(page,operations);await page.goto('/?page=pets');
 await expect(page.getByRole('heading',{name:'Haustiere'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Luna'})).toHaveClass(/active/);
 await page.getByRole('button',{name:'Gefüttert'}).click();
 expect(operations.at(-1)).toMatchObject({method:'POST',path:'/pets/pet-1/care/'});expect(operations.at(-1).body.kind).toBe('feed');
 await page.getByRole('button',{name:'Gassi starten'}).click();expect(operations.at(-1).body.kind).toBe('walk');
 await expect(page.getByRole('button',{name:'Gassi beenden'})).toBeVisible();
 await page.getByRole('button',{name:'Milo'}).click();await expect(page.getByRole('button',{name:'Gassi starten'})).toBeVisible();
 await page.getByRole('button',{name:'Wasser'}).click();expect(operations.at(-1)).toMatchObject({method:'POST',path:'/pets/pet-2/care/'});
 await page.getByRole('button',{name:'Luna'}).click();await expect(page.getByRole('button',{name:'Gassi beenden'})).toBeVisible();
 await page.getByRole('button',{name:'Gassi beenden'}).click();expect(operations.at(-1)).toMatchObject({method:'PATCH',path:'/pets/care/log-2/'});expect(operations.at(-1).body.ended_at).toBeTruthy();
});

test('pet module can be opted into main navigation without replacing existing sections',async({page})=>{
 await installApiMocks(page,{language:'de'});await installPetMocks(page,[],{showNav:true});await page.goto('/');
 const nav=page.locator('.bottom-nav');await expect(nav.getByRole('button',{name:'Tiere'})).toBeVisible();await expect(nav.getByRole('button',{name:'Heute'})).toBeVisible();await expect(nav.getByRole('button',{name:'Mehr'})).toBeVisible();
 await nav.getByRole('button',{name:'Tiere'}).click();await expect(page).toHaveURL(/page=pets/);await expect(page.getByRole('heading',{name:'Haustiere'})).toBeVisible();
});

test('pet care queues offline entries and syncs them idempotently when back online',async({page})=>{
 const operations=[];await installApiMocks(page,{language:'de'});await installPetMocks(page,operations);await page.goto('/?page=pets');
 await page.evaluate(()=>Object.defineProperty(navigator,'onLine',{configurable:true,get:()=>false}));
 await page.getByRole('button',{name:'Gefüttert'}).click();
 await expect(page.getByText('1 Eintrag wartet auf Synchronisierung')).toBeVisible();
 expect(operations.filter(row=>row.path==='/pets/pet-1/care/')).toHaveLength(0);
 await page.evaluate(()=>{Object.defineProperty(navigator,'onLine',{configurable:true,get:()=>true});window.dispatchEvent(new Event('online'))});
 await expect(page.getByText('1 Eintrag wartet auf Synchronisierung')).toBeHidden();
 await expect.poll(()=>operations.filter(row=>row.path==='/pets/pet-1/care/'&&row.method==='POST').length).toBe(1);
 const ids=operations.filter(row=>row.path==='/pets/pet-1/care/').map(row=>row.body.client_event_id);expect(ids[0]).toBeTruthy();
});
