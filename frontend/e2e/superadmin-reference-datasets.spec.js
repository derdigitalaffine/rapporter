import {test,expect} from '@playwright/test';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const adminUser={id:99,username:'root',email:'root@example.test',email_verified:true,is_superadmin:true};
const session={id:'admin-session',current:true,client:'Chromium',auth_method:'password',created_at:'2026-10-17T17:00:00Z',last_seen_at:'2026-10-17T18:00:00Z',last_reauthenticated_at:'2026-10-17T18:00:00Z',fresh_until:'2026-10-17T18:10:00Z',absolute_expires_at:'2027-01-01T00:00:00Z'};

const previewDataset={
 id:'11111111-1111-4111-8111-111111111111',dataset_id:'shopping.de.food-lexicon.sample',dataset_type:'lexicon',schema_version:1,version:'2026-10-17.1',source_adapter:'operator_upload',source_url:'https://example.test/reference/lexicon',source_revision:'fixture-1',locale:'de-DE',country:'DE',region:'',licence:'CC0-1.0',attribution:'Fixture authors',redistribution:'adopt',checksum:`sha256:${'a'.repeat(64)}`,coverage:{completeness_claim:false},quality:{ambiguous_input_policy:'ABSTAIN'},dependencies:[],state:'preview',state_revision:3,package_size_bytes:4096,record_count:15,runtime_eligible:true,validation:{valid:true,runtime_eligible:true,blockers:[],files:{'lexicon.json':15},records:15,materialized:true},validation_error:'',installed_at:'2026-10-17T18:00:00Z',validated_at:'2026-10-17T18:00:01Z',activated_at:null,updated_at:'2026-10-17T18:00:01Z',manifest:{privacy:{contains_private_household_data:false}}};

async function installReferenceMocks(page){
 const state={dataset:{...previewDataset},activateAttempts:0,reauths:0};
 await page.route('**/api/superadmin/auth/session/',route=>json(route,{authenticated:true,user:adminUser,session,fresh:true}));
 await page.route('**/api/superadmin/auth/refresh/',route=>json(route,{authenticated:true,user:adminUser,session,fresh:true}));
 await page.route('**/api/superadmin/auth/reauth/password/',route=>{state.reauths+=1;expect(route.request().postDataJSON()).toEqual({password:'admin-password'});return json(route,{reauthenticated:true,session})});
 await page.route('**/api/superadmin/reference-datasets/**',route=>{
   const request=route.request();const url=new URL(request.url());const method=request.method();
   if(url.pathname==='/api/superadmin/reference-datasets/'&&method==='GET')return json(route,{results:[state.dataset],truncated:false,limit:100});
   if(url.pathname===`/api/superadmin/reference-datasets/${state.dataset.id}/`&&method==='GET')return json(route,{dataset:state.dataset,active_other_version:null,events:state.dataset.state==='active'?[{id:'event-1',action:'activate',from_version:'',to_version:state.dataset.version,state_revision:state.dataset.state_revision,reason_code:'operator_activate',created_at:'2026-10-17T18:02:00Z'}]:[]});
   if(url.pathname===`/api/superadmin/reference-datasets/${state.dataset.id}/activate/`&&method==='POST'){
     state.activateAttempts+=1;
     expect(request.postDataJSON()).toEqual({expected_revision:state.dataset.state_revision});
     if(state.activateAttempts===1)return json(route,{detail:'Fresh reauthentication required.','code':'reauth_required'},403);
     state.dataset={...state.dataset,state:'active',state_revision:state.dataset.state_revision+2,activated_at:'2026-10-17T18:02:00Z',updated_at:'2026-10-17T18:02:00Z'};
     return json(route,{dataset:state.dataset});
   }
   return json(route,{detail:'not found'},404);
 });
 return state;
}

test('superadmin reference data flow previews rights and requires reauth before activation',async({page})=>{
 const state=await installReferenceMocks(page);
 await page.goto('/superadmin/?section=reference-data');

 await expect(page.getByRole('heading',{name:'Datenpakete sicher verwalten'})).toBeVisible();
 await expect(page.getByText('Der Einkauf funktioniert vollständig ohne Referenzpakete.')).toHaveCount(0);
 await expect(page.getByText('shopping.de.food-lexicon.sample',{exact:true})).toBeVisible();
 await page.getByText('shopping.de.food-lexicon.sample',{exact:true}).click();

 await expect(page.getByText('Freigegeben',{exact:true})).toBeVisible();
 await expect(page.getByText('CC0-1.0',{exact:true})).toBeVisible();
 await expect(page.getByText('Validiert',{exact:true})).toBeVisible();
 await expect(page.getByText('15',{exact:true}).first()).toBeVisible();

 await page.getByRole('button',{name:'Version aktivieren'}).click();
 await expect(page.getByRole('heading',{name:'Admin-Identität bestätigen'})).toBeVisible();
 await page.getByLabel('Passwort').fill('admin-password');
 await page.getByRole('button',{name:'Bestätigen & fortfahren'}).click();

 await expect.poll(()=>state.reauths).toBe(1);
 await expect.poll(()=>state.activateAttempts).toBe(2);
 await expect(page.getByText('Aktiv',{exact:true}).first()).toBeVisible();
 await expect(page.getByRole('button',{name:'Deaktivieren'})).toBeVisible();
});

test('reference data operator flow stays usable at 390px without horizontal overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await installReferenceMocks(page);
 await page.goto('/superadmin/?section=reference-data');

 await expect(page.getByRole('heading',{name:'Datenpakete sicher verwalten'})).toBeVisible();
 await page.getByText('shopping.de.food-lexicon.sample',{exact:true}).click();
 await expect(page.getByText('Rechte & Provenienz')).toBeVisible();
 await expect(page.getByRole('button',{name:'Version aktivieren'})).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
 expect(overflow).toBeLessThanOrEqual(0);
});
