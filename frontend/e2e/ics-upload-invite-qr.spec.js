import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,path='/?page=integrations'){
 await installApiMocks(page,{language:'de'});
 await page.goto(path);
 await page.waitForLoadState('networkidle');
}

test('city waste calendar accepts a downloaded ICS file',async({page})=>{
 await installApiMocks(page,{language:'de'});
 const catalog=[{
  id:'waste_kl_city',kind:'waste',name:'Müllkalender Stadt Kaiserslautern',
  description:'Heruntergeladene ICS-Datei der Stadtbildpflege importieren.',
  help_url:'https://www.kaiserslautern.de/',
  fields:[{key:'ics_file',label:'ICS-Datei',type:'file',accept:'.ics,text/calendar',required:true}],
  defaults:{adapter:'waste_kl_city',provider:'Stadtbildpflege Kaiserslautern',event_type:'waste.collection',static_ics:true},
 }];
 await page.route('**/api/integration-hub/catalog/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(catalog)}));
 await page.route('**/api/integration-hub/connect/',route=>route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({synced:1,source:{id:'waste-upload',family:'family-1',kind:'waste',name:'Müllkalender Stadt Kaiserslautern',config:{adapter:'waste_kl_city',ics_content:'••••••••'}}})}));
 await page.goto('/?page=integrations');
 await page.waitForLoadState('networkidle');
 const card=page.locator('.catalog-card').filter({hasText:'Müllkalender Stadt Kaiserslautern'});
 await card.getByRole('button',{name:'Konfigurieren'}).click();
 const dialog=page.getByRole('dialog');
 const input=dialog.locator('input[type="file"]');
 await expect(input).toHaveAttribute('accept',/.ics/);
 const ics='BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:waste-1\r\nDTSTART;VALUE=DATE:20261010\r\nSUMMARY:Restmüll\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n';
 await input.setInputFiles({name:'abfallkalender.ics',mimeType:'text/calendar',buffer:Buffer.from(ics)});
 const requestPromise=page.waitForRequest(request=>request.url().endsWith('/api/integration-hub/connect/')&&request.method()==='POST');
 await dialog.getByRole('button',{name:'Verbinden'}).click();
 const request=await requestPromise;
 expect(request.headers()['content-type']).toContain('multipart/form-data');
 expect(request.postData()).toContain('abfallkalender.ics');
 await expect(page.getByText('Müllkalender Stadt Kaiserslautern ist bereit',{exact:true})).toBeVisible();
});

test('new member invitation shows a QR code for the invite page',async({page})=>{
 await boot(page,'/?page=members');
 await page.getByRole('button',{name:'Person einladen'}).click();
 let dialog=page.getByRole('dialog');
 await dialog.getByLabel('Anzeigename').fill('Oma');
 await dialog.getByRole('button',{name:/Weiter zu Rolle/}).click();
 dialog=page.getByRole('dialog');
 await dialog.getByText('Gast',{exact:true}).first().click();
 await dialog.getByRole('button',{name:'Einladung erstellen'}).click();
 const qr=dialog.locator('.invite-qr-image');
 await expect(qr).toBeVisible();
 await expect(qr).toHaveAttribute('src',/^data:image\/png;base64,/);
 await expect(dialog.getByText('Mit dem Handy scannen',{exact:true})).toBeVisible();
});
