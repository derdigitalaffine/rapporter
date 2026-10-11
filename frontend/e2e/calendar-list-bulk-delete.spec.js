import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const isoIn=hours=>new Date(Date.now()+hours*3600000).toISOString();

async function bootList(page,{mobile=false}={}){
 if(mobile)await page.setViewportSize({width:390,height:844});
 const state=await installApiMocks(page);
 await page.goto('/?page=calendar&view=list');
 return state;
}

test('calendar list bulk-selects and deletes only native FamilyOS events',async({page})=>{
 const state=await installApiMocks(page);
 state.events.push(
  {id:'event-2',family:state.family.id,source:null,type:'calendar.event',title:'Elternabend intern',starts_at:isoIn(7),ends_at:isoIn(8),actionable:false,payload:{provider:'fam-uh-le',location:'Schule',description:'',recurrence:''}},
  {id:'event-external',family:state.family.id,source:'source-work',source_meta:{id:'source-work',name:'Arbeit',kind:'ics',presentation:{icon:'calendar',tone:'blue',label:'Arbeitskalender'}},type:'calendar.event',title:'Arbeitskalender read-only',starts_at:isoIn(9),ends_at:isoIn(10),actionable:false,payload:{}},
 );
 await page.goto('/?page=calendar&view=list');

 await page.getByRole('button',{name:'Auswählen',exact:true}).click();
 const checkboxes=page.getByRole('checkbox');
 await expect(checkboxes).toHaveCount(2);
 await expect(page.getByRole('checkbox',{name:'Kinderarzt auswählen'})).toBeVisible();
 await expect(page.getByRole('checkbox',{name:'Elternabend intern auswählen'})).toBeVisible();
 await expect(page.getByRole('checkbox',{name:/Arbeitskalender/})).toHaveCount(0);
 await expect(page.getByRole('img',{name:/Nicht auswählbar/})).toBeVisible();

 const first=page.getByRole('checkbox',{name:'Kinderarzt auswählen'});
 const second=page.getByRole('checkbox',{name:'Elternabend intern auswählen'});
 await first.focus();await first.press('Space');
 await second.focus();await second.press('Space');
 await expect(page.getByText('2 ausgewählt',{exact:true})).toBeVisible();

 await page.getByRole('button',{name:'Auswahl löschen',exact:true}).click();
 const dialog=page.getByRole('alertdialog');
 await expect(dialog).toContainText('Ausgewählt: 2');
 await dialog.getByRole('button',{name:'Auswahl löschen',exact:true}).click();

 await expect.poll(()=>state.events.some(event=>event.id==='event-1'||event.id==='event-2')).toBe(false);
 expect(state.events.some(event=>event.id==='event-external')).toBe(true);
 await expect(page.getByText('Kinderarzt',{exact:true})).toHaveCount(0);
 await expect(page.getByText('Elternabend intern',{exact:true})).toHaveCount(0);
 await expect(page.getByText('Arbeitskalender read-only',{exact:true})).toBeVisible();
});

test('compact list density is smaller, mobile-safe and survives reload',async({page})=>{
 await bootList(page,{mobile:true});
 const eventRow=page.locator('.agenda-event').filter({hasText:'Kinderarzt'});
 const normalBox=await eventRow.boundingBox();
 expect(normalBox).not.toBeNull();

 await page.getByRole('button',{name:'Kompakt',exact:true}).click();
 await expect(page.locator('.agenda-days')).toHaveClass(/calendar-list-compact/);
 const compactBox=await eventRow.boundingBox();
 expect(compactBox).not.toBeNull();
 expect(compactBox.height).toBeLessThan(normalBox.height);
 expect(await page.evaluate(()=>localStorage.getItem('familyos:calendar:list-density:v1'))).toBe('compact');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);

 await page.reload();
 await expect(page.getByRole('button',{name:'Kompakt',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.agenda-days')).toHaveClass(/calendar-list-compact/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});