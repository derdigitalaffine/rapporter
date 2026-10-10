import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
async function boot(page,language='de'){
 await installApiMocks(page,{language});let rows=[];
 await page.route('**/api/board/**',async route=>{const request=route.request(),method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
 if(method==='GET')return route.fulfill({json:{count:rows.length,next:null,results:rows}});
 if(method==='POST'){const text=request.postData().match(/name="text"\r\n\r\n([^]*?)\r\n--/)?.[1]||'';const row={id:'post-1',text,author_name:'Alex',created_at:new Date().toISOString(),can_edit:true,can_delete:true,images:[]};rows.unshift(row);return route.fulfill({status:201,json:row})}
 if(method==='PATCH'){rows[0]={...rows[0],...body};return route.fulfill({json:rows[0]})}
 if(method==='DELETE'){rows=[];return route.fulfill({status:204,body:''})}
 });await page.goto('/?page=board');
}
test('publish, edit, reload and delete family post',async({page})=>{
 test.setTimeout(60000);
 await boot(page);
 await page.getByRole('button',{name:'Neuer Beitrag',exact:true}).click();
 let form=page.locator('.board-compose');await expect(form).toBeVisible();
 await form.getByLabel('Mitteilung',{exact:true}).fill('Wir treffen uns im Garten.');
 await form.getByRole('button',{name:'Veröffentlichen',exact:true}).click();
 const post=page.locator('.board-post').first();await expect(post).toContainText('Wir treffen uns im Garten.');
 await post.getByRole('button',{name:'Bearbeiten',exact:true}).click();
 form=page.locator('.board-compose');await expect(form).toBeVisible();
 await form.getByLabel('Mitteilung',{exact:true}).fill('Wir treffen uns um 16 Uhr.');
 await form.getByRole('button',{name:'Speichern',exact:true}).click();
 await page.reload();await expect(page.locator('.board-post')).toContainText('16 Uhr');
 await page.locator('.board-post').getByRole('button',{name:'Löschen',exact:true}).click();
 await page.getByRole('alertdialog').getByRole('button',{name:'Löschen',exact:true}).click();
 await expect(page.locator('.board-post')).toHaveCount(0);
});
test('English and narrow layout',async({page})=>{await page.setViewportSize({width:390,height:844});await boot(page,'en');await expect(page.getByRole('heading',{name:'Family board',exact:true})).toBeVisible();await page.getByRole('button',{name:'New post',exact:true}).click();await expect(page.getByLabel('Message',{exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()});
