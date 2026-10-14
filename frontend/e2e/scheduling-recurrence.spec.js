import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const directEventProfile={ranking_version:1,cold_start_threshold:5,preferences:{smart_ranking_enabled:true,context_ranking_enabled:true,time_patterns_enabled:false,direct_mode:true,direct_action_id:'event',max_quick_actions:4,pinned_action_ids:[],hidden_action_ids:[],manual_order:[],learning_scope:'family'},stats:[]};

async function bootCalendar(page){
 await installApiMocks(page,{dismissOnboarding:true});
 await page.route('**/api/create-actions/**',async route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(directEventProfile)}));
 await page.route('**/api/scheduling/preview/**',async route=>{
  const body=route.request().postDataJSON()||{};
  const recurrence=body.text?{frequency:'quarterly',interval:1,nth_weekdays:[{weekday:'MO',ordinal:1}]}:body.rule?.recurrence;
  const anchor=body.anchor_date||body.rule?.anchor_date||'2026-10-14';
  return route.fulfill({json:{rule:{version:'scheduling-rule-v1',timezone:'Europe/Berlin',time_mode:'wall_clock',anchor_date:anchor,recurrence},summary:'Jedes Quartal · erster Montag',occurrences:['2027-01-04','2027-04-05','2027-07-05','2027-10-04','2028-01-03'],timezone:'Europe/Berlin'}});
 });
 await page.goto('/?page=calendar');
 await page.waitForLoadState('networkidle');
}

test('calendar recurrence uses the same natural-language rule and preview as todos',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await bootCalendar(page);
 let created=null;
 await page.route('**/api/events/',async route=>{
  if(route.request().method()!=='POST')return route.fallback();
  created=route.request().postDataJSON();
  return route.fulfill({status:201,json:{id:'event-created',...created}});
 });
 await page.locator('.global-create-fab').click();
 const dialog=page.getByRole('dialog',{name:'Termin hinzufügen'});
 await dialog.getByLabel('Titel').fill('Quartalsplanung');
 await dialog.getByRole('button',{name:'Weitere Details'}).click();
 await dialog.getByLabel('In eigenen Worten').fill('immer am ersten Montag im Quartal');
 await dialog.getByRole('button',{name:'Erkennen',exact:true}).click();
 await expect(dialog.getByLabel('Wiederholung',{exact:true})).toHaveValue('quarterly');
 await expect(dialog.getByText(/erster Montag/)).toBeVisible();
 await expect(dialog.locator('.scheduling-recurrence-preview li')).toHaveCount(5);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
 await dialog.getByRole('button',{name:'Speichern',exact:true}).click();
 await expect.poll(()=>created?.payload?.recurrence?.frequency).toBe('quarterly');
 expect(created.payload.recurrence.nth_weekdays).toEqual([{weekday:'MO',ordinal:1}]);
});
