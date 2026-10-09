import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api';

test('delivery detail and quiet hours persist independently of device permission',async({page})=>{
 await installApiMocks(page);
 const prefs={tasks:true,task_assigned:true,shopping:true,calendar:true,family_updates:true,messages:true,routines:true,detail_level:'summary',quiet_hours_enabled:false,quiet_start:'22:00:00',quiet_end:'07:00:00'};
 await page.route('**/api/push/preferences/**',async route=>{if(route.request().method()==='PATCH')Object.assign(prefs,route.request().postDataJSON());await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(prefs)})});
 await page.goto('/?page=notifications');
 await expect(page.getByRole('radio',{name:/Zusammengefasst/})).toBeChecked();
 await page.getByRole('radio',{name:/Nur Wichtiges/}).check();
 await expect.poll(()=>prefs.detail_level).toBe('important');
 await page.getByRole('checkbox',{name:'Ruhezeiten',exact:true}).check();
 await expect(page.getByLabel('Von',{exact:true})).toBeVisible();
 await page.getByLabel('Von',{exact:true}).fill('21:00');
 await expect.poll(()=>prefs.quiet_start).toBe('21:00');
 await page.reload();
 await expect(page.getByRole('radio',{name:/Nur Wichtiges/})).toBeChecked();
 await expect(page.getByLabel('Von',{exact:true})).toHaveValue('21:00');
});
