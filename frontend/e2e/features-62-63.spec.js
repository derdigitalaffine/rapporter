import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function installLoyaltyApi(page){
 let cards=[];
 await page.route('**/api/loyalty-cards/**',async route=>{
  const request=route.request();const method=request.method();const url=new URL(request.url());const path=url.pathname;let body={};try{body=request.postDataJSON()||{}}catch{}
  const json=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  if(path.endsWith('/sync/')&&method==='GET')return json(cards);
  if(path.endsWith('/loyalty-cards/')&&method==='POST'){
   const shared=(body.shared_with_ids||[]).map(id=>({id,user:id==='member-2'?2:1,name:id==='member-2'?'Sam':'Alex',role:id==='member-2'?'adult':'owner'}));
   const card={id:`card-${cards.length+1}`,...body,holder_display:body.holder_name||'',created_by:1,created_by_name:'alex',shared_with:shared,can_edit:true,created_at:new Date().toISOString(),updated_at:new Date().toISOString()};cards=[card,...cards];return json(card,201);
  }
  const match=path.match(/\/loyalty-cards\/([^/]+)\/$/);if(match){const index=cards.findIndex(card=>card.id===match[1]);if(method==='PATCH'&&index>=0){const shared=(body.shared_with_ids||[]).map(id=>({id,user:id==='member-2'?2:1,name:id==='member-2'?'Sam':'Alex',role:id==='member-2'?'adult':'owner'}));cards[index]={...cards[index],...body,shared_with:shared,updated_at:new Date().toISOString()};return json(cards[index])}if(method==='DELETE'&&index>=0){cards.splice(index,1);return route.fulfill({status:204,body:''})}}
  return json([]);
 });
 return {getCards:()=>cards,revokeAll:()=>{cards=[]}};
}

test('notification preferences are separate per-family controls',async({page})=>{
 await installApiMocks(page,{language:'de'});
 const prefs={membership:'member-1',family:'family-1',tasks:true,task_assigned:true,shopping:true,calendar:true,family_updates:true,messages:true,routines:true};
 await page.route('**/api/push/preferences/**',async route=>{const request=route.request();if(request.method()==='PATCH'){Object.assign(prefs,request.postDataJSON());return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(prefs)})}return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(prefs)})});
 await page.goto('/?page=notifications');await page.waitForLoadState('networkidle');
 const shopping=page.locator('.preference-row').filter({hasText:'Einkauf'}).locator('input');
 await expect(shopping).toBeChecked();await shopping.uncheck();await expect(shopping).not.toBeChecked();
 expect(prefs.shopping).toBe(false);
 await expect(page.getByText('Diese Auswahl ist unabhängig von der Gerätefreigabe oben')).toBeVisible();
});

test('notification deep link resolves the concrete task and survives reload',async({page})=>{
 await installApiMocks(page,{language:'de'});
 await page.route('**/api/tasks/task-1/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({id:'task-1',family:'family-1',task_list:'tasks-1',title:'Wäsche aufhängen',notes:'Balkon',list_name:'Alltag',assignee_name:'Alex'})}));
 await page.goto('/?page=tasks&task=task-1&list=tasks-1');
 const target=page.getByRole('dialog');
 await expect(target.getByRole('heading',{name:'Wäsche aufhängen'})).toBeVisible();
 await expect(target.getByText('Alltag')).toBeVisible();
 await expect(target.getByText('Balkon')).toBeVisible();
 await page.reload();
 await expect(page.getByRole('dialog').getByRole('heading',{name:'Wäsche aufhängen'})).toBeVisible();
 await expect(page).toHaveURL(/task=task-1/);
});

test('missing notification target falls back to its parent area',async({page})=>{
 await installApiMocks(page,{language:'de'});
 await page.goto('/?page=calendar&event=missing');
 await expect(page.getByRole('heading',{name:'Kalender'})).toBeVisible();
 await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('manual loyalty card creation, sharing and offline revocation sync',async({page,context})=>{
 await installApiMocks(page,{language:'de'});const loyalty=await installLoyaltyApi(page);
 await page.goto('/?page=more');await page.waitForLoadState('networkidle');
 await page.getByRole('button',{name:'Bonuskarten',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Bonuskarten',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Karte hinzufügen'}).click();
 await page.getByLabel('Kartenname').fill('PAYBACK');
 await page.getByLabel('Kundennummer').fill('47110815');
 await page.getByLabel('Barcode-/Kartenwert').fill('123456789012');
 await page.locator('.sharing-row').filter({hasText:'Sam'}).locator('input').check();
 await page.getByRole('button',{name:'Karte speichern'}).click();
 await expect(page.getByRole('button',{name:/PAYBACK/})).toBeVisible();
 await page.getByRole('button',{name:/PAYBACK/}).click();
 await expect(page.locator('.loyalty-readable',{hasText:'47110815'})).toBeVisible();
 await expect(page.locator('.barcode-stage canvas')).toBeVisible();
 await page.getByRole('button',{name:'Zurück'}).click();

 await context.setOffline(true);
 await page.getByRole('button',{name:'Zurück'}).click();
 await page.getByRole('button',{name:'Bonuskarten',exact:true}).click();
 await expect(page.getByText('Offline-Modus')).toBeVisible();
 await expect(page.getByRole('button',{name:/PAYBACK/})).toBeVisible();

 loyalty.revokeAll();await context.setOffline(false);
 await expect(page.getByText('Noch keine Bonuskarte sichtbar.')).toBeVisible();
 await context.setOffline(true);
 await page.getByRole('button',{name:'Zurück'}).click();
 await page.getByRole('button',{name:'Bonuskarten',exact:true}).click();
 await expect(page.getByText('Noch keine Bonuskarte sichtbar.')).toBeVisible();
});
