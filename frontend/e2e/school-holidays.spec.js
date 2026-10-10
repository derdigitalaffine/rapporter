import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
const catalog={id:'rlp_school_holidays',kind:'school',name:'Schulferien Rheinland-Pfalz',description:'Amtliche Ferien. Bewegliche Ferientage legt die Schule fest.',help_url:'https://bm.rlp.de/service/ferientermine',singleton:true,fields:[],defaults:{adapter:'rlp_school_holidays'}};
test('official school holidays connect without credentials and render as a read-only holiday period',async({page})=>{
 const state=await installApiMocks(page);state.integrations.length=0;
 await page.route('**/api/integration-hub/catalog/',route=>route.fulfill({json:[catalog]}));
 await page.route('**/api/integration-hub/connect/',async route=>{
  const body=route.request().postDataJSON();expect(body.catalog_id).toBe('rlp_school_holidays');expect(body.values).toEqual({});
  const source={id:'school-source',family:'family-1',name:catalog.name,kind:'school',enabled:true,config:catalog.defaults,last_sync_status:'success',last_success_at:new Date().toISOString()};state.integrations.push(source);
  state.events.push({id:'holiday',family:'family-1',source:source.id,type:'school.holiday',title:'Sommerferien RLP Schuljahr 2028/2029',starts_at:'2028-07-02T22:00:00Z',ends_at:'2028-08-11T22:00:00Z',payload:{all_day:true,date_start:'2028-07-03',date_end_exclusive:'2028-08-12',provider:'Ministerium für Bildung Rheinland-Pfalz',source_url:catalog.help_url,description:'Bewegliche Ferientage legt jede Schule selbst fest; sie sind hier nicht enthalten.'}});
  await route.fulfill({status:201,json:{source,synced:1}});
 });
 await page.goto('/?page=integrations');
 const card=page.locator('.catalog-card').filter({hasText:catalog.name});await card.getByRole('button',{name:'Einrichten'}).click();
 const setup=page.getByRole('dialog');await expect(setup).toContainText('Keine Zugangsdaten nötig');await expect(setup.locator('input')).toHaveCount(0);await setup.getByRole('button',{name:'Verbinden',exact:true}).click();
 await expect(card.getByRole('button',{name:'Verbunden',exact:true})).toBeDisabled();
 await page.goto('/?page=calendar');
 await page.getByRole('button',{name:'Liste',exact:true}).click();
 const holiday=page.locator('.agenda-holiday').filter({hasText:'Sommerferien RLP'});
 await expect(holiday).toBeVisible();await expect(holiday).toContainText('FERIEN');await expect(holiday).toContainText('3. Juli – 11. August');await expect(holiday.locator('.special-rail')).toHaveCount(1);await holiday.click();
 const detail=page.getByRole('dialog');await expect(detail).toContainText('3. Juli');await expect(detail).toContainText('11. August 2028');await expect(detail).toContainText('Bewegliche Ferientage');await expect(detail.getByRole('link',{name:'Amtliche Ferientermine'})).toHaveAttribute('href',catalog.help_url);await expect(detail.getByRole('button',{name:'Termin bearbeiten'})).toHaveCount(0);
});
