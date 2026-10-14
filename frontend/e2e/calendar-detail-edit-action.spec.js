import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const directEventProfile={
  ranking_version:1,
  cold_start_threshold:5,
  preferences:{smart_ranking_enabled:true,context_ranking_enabled:true,time_patterns_enabled:false,direct_mode:true,direct_action_id:'event',max_quick_actions:4,pinned_action_ids:[],hidden_action_ids:[],manual_order:[],learning_scope:'family'},
  stats:[],
};

async function routeDirectEventCreate(page){
  await page.route('**/api/create-actions/**',async route=>{
    if(route.request().method()==='POST')return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({...directEventProfile,accepted:true,deduplicated:false})});
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(directEventProfile)});
  });
}

test('new FamilyOS event keeps edit action visible without scrolling the sheet',async({page})=>{
  await page.setViewportSize({width:390,height:640});
  await installApiMocks(page,{dismissOnboarding:true});
  await routeDirectEventCreate(page);
  await page.goto('/?page=calendar&view=list');
  await page.waitForLoadState('networkidle');

  const fab=page.locator('.global-create-fab');
  await expect(fab).toHaveAttribute('aria-label','Termin hinzufügen');
  await fab.click();
  const editor=page.getByRole('dialog',{name:'Termin hinzufügen'});
  await expect(editor).toBeVisible();
  await editor.getByLabel('Titel').fill('Eigener neuer Termin');
  await editor.getByRole('button',{name:'Weitere Details'}).click();
  await editor.getByLabel('Notizen').fill(Array.from({length:24},(_,index)=>`Notiz ${index+1}: zusätzlicher Inhalt`).join('\n'));
  await editor.getByRole('button',{name:'Speichern',exact:true}).click();
  await expect(editor).toBeHidden();

  const row=page.locator('.agenda-event').filter({hasText:'Eigener neuer Termin'}).first();
  await expect(row).toBeVisible();
  await row.click();

  const detail=page.getByRole('dialog').filter({hasText:'Eigener neuer Termin'});
  await expect(detail).toBeVisible();
  const editButton=detail.getByRole('button',{name:'Termin bearbeiten',exact:true});
  await expect(editButton).toBeVisible();
  await expect.poll(async()=>detail.locator('.event-detail-body').evaluate(node=>node.scrollHeight>node.clientHeight)).toBe(true);
  const box=await editButton.boundingBox();
  expect(box).not.toBeNull();
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y+box.height).toBeLessThanOrEqual(640);

  await editButton.click();
  await expect(page.getByRole('dialog',{name:'Termin bearbeiten'})).toBeVisible();
});
