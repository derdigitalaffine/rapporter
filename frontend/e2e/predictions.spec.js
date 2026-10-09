import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

test('shopping prediction is explainable and only added after explicit confirmation',async({page})=>{
 await installApiMocks(page);let suggestions=[{id:'shopping:milch',kind:'shopping',subject_key:'milch',title:'Milch',due_at:'2026-10-10T08:00:00Z',interval_days:5.2,confidence:.84,confidence_label:'high',sample_count:8,quantity:'2',category:'Molkerei'}];let added=false;
 await page.route('**/api/predictions/**',async route=>{if(route.request().url().includes('/feedback/')){suggestions=[];return json(route,{ok:true})}return json(route,{suggestions})});await page.route('**/api/smart/shopping/quick-add/',route=>{added=true;return json(route,{id:'predicted-item',name:'Milch'},201)});
 await page.goto('/?page=shopping');await expect(page.getByText('Wahrscheinlich bald wieder nötig')).toBeVisible();await expect(page.getByText('Milch',{exact:true}).first()).toBeVisible();await expect(page.getByText(/84 %/)).toBeVisible();expect(added).toBe(false);await page.getByRole('button',{name:'Hinzufügen'}).click();await expect.poll(()=>added).toBe(true);await expect(page.getByText('Wahrscheinlich bald wieder nötig')).toHaveCount(0);
});

test('routine editor no longer asks for an interval and explains learning',async({page})=>{await installApiMocks(page);await page.route('**/api/predictions/**',route=>json(route,{suggestions:[]}));await page.goto('/?page=routines');const routine=page.locator('.row-main-button').first();await expect(routine).toBeVisible();await routine.click();await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByText(/FamilyOS lernt den Rhythmus|Meist etwa alle/)).toBeVisible();await expect(page.getByLabel(/Intervall|Interval/i)).toHaveCount(0)});
