import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,{canPlan=true,path='/?page=birthdays'}={}){
 await installApiMocks(page,{dismissOnboarding:true});const rows=[{key:'member:member-2',id:'member-2',kind:'member',name:'Sam',birth_month:3,birth_day:12,birth_year:null,next_occurrence:'2027-03-12',days_until:12,turning_age:null,can_plan:canPlan,...(canPlan?{gift_status:'none',idea_text:''}:{})}];const requests=[];
 await page.route('**/api/birthdays/**',route=>route.fulfill({json:{birthdays:rows,can_manage:true}}));
 await page.route('**/api/birthday-people/**',route=>{const body=route.request().postDataJSON();requests.push(body);const person={...body,id:'birthday-new',key:'person:birthday-new',kind:'person',next_occurrence:'2027-04-09',days_until:40,turning_age:null,can_plan:true,gift_status:'none',idea_text:''};rows.push(person);return route.fulfill({status:201,json:person})});
 await page.route('**/api/birthday-gift-plans/**',route=>{const body=route.request().postDataJSON();requests.push(body);Object.assign(rows[0],{idea_text:body.idea_text,gift_status:body.status==='none'?'idea':body.status,...(body.action==='task'?{linked_task:'gift-task'}:{})});return route.fulfill({json:rows[0]})});
 await page.goto(path);await page.waitForLoadState('networkidle');return {rows,requests};
}
test('birthdays · add external person without year and keep existing profile source',async({page})=>{
 const state=await boot(page);await page.locator('.birthday-actions').getByRole('button',{name:'Geburtstag hinzufügen',exact:true}).click();const dialog=page.getByRole('dialog');await dialog.getByLabel('Name',{exact:true}).fill('Oma');await dialog.getByLabel('Tag',{exact:true}).fill('9');await dialog.getByLabel('Monat',{exact:true}).fill('4');await dialog.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.getByText(/Oma · Geburtstag/)).toBeVisible();expect(state.requests[0].birth_year).toBe(null);await expect(page.locator('.birthday-actions').getByRole('link',{name:'Mein Geburtstag im Profil'})).toHaveAttribute('href','/?page=profile');
});
test('birthdays · gift idea, existing task integration and reload-safe detail',async({page})=>{
 const state=await boot(page);await page.getByRole('button',{name:'Geschenk planen',exact:true}).click();let dialog=page.getByRole('dialog',{name:'Sam'});await dialog.getByLabel('Geschenkidee').fill('Buch');await dialog.getByRole('button',{name:'Geschenkaufgabe erstellen'}).click();await expect(dialog.getByRole('button',{name:'Geschenkaufgabe erstellen'})).toBeDisabled();expect(state.requests[0].action).toBe('task');await page.reload();dialog=page.getByRole('dialog',{name:'Sam'});await expect(dialog).toBeVisible();await expect(dialog.getByLabel('Geschenkidee')).toHaveValue('Buch');
});
test('birthdays · recipient receives no gift controls or details',async({page})=>{
 await boot(page,{canPlan:false,path:'/?page=birthdays&birthday=member:member-2'});const dialog=page.getByRole('dialog',{name:'Sam'});await expect(dialog).toBeVisible();await expect(dialog.getByLabel('Geschenkidee')).toHaveCount(0);await expect(dialog.getByRole('button',{name:'Geschenkaufgabe erstellen'})).toHaveCount(0);await expect(page.getByText('Geschenk planen',{exact:true})).toHaveCount(0);
});
for(const viewport of [{width:390,height:844},{width:1024,height:768},{width:1440,height:900}])test(`birthdays · responsive ${viewport.width}×${viewport.height}`,async({page})=>{await page.setViewportSize(viewport);await boot(page);const width=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:window.innerWidth}));expect(width.scroll).toBeLessThanOrEqual(width.width+1)});
