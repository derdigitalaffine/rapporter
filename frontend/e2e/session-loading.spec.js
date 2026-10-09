import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function boot(page,path='/'){
 await page.goto(path);
}

test('initial dashboard shows loading instead of a false empty state',async({page})=>{
 await installApiMocks(page,{language:'de'});
 await page.route('**/api/families/',async route=>{await sleep(700);await route.fallback()});
 await boot(page);
 await expect(page.getByText('Daten werden geladen …',{exact:true})).toBeVisible();
 await expect(page.getByText('Alles erledigt',{exact:true})).toHaveCount(0);
 await expect(page.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
});

test('tasks keep loading, error and empty states distinct with retry',async({page})=>{
 await installApiMocks(page,{language:'de'});
 let failTasks=true;
 await page.route('**/api/tasks/',async route=>{
  if(route.request().method()==='GET'&&failTasks){failTasks=false;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Dienst vorübergehend nicht erreichbar'})})}
  return route.fallback();
 });
 await boot(page,'/?page=tasks');
 await expect(page.getByText('Daten konnten nicht geladen werden.',{exact:true})).toBeVisible();
 await expect(page.getByText('Alles erledigt',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:/Erneut versuchen/}).click();
 await expect(page.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
});

test('expired session is shown once and restores the previous route after login',async({page})=>{
 await installApiMocks(page,{language:'de'});
 let expireTasks=true;
 await page.route('**/api/tasks/',async route=>{
  if(route.request().method()==='GET'&&expireTasks){expireTasks=false;return route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({detail:'expired'})})}
  return route.fallback();
 });
 await page.route('**/api/auth/refresh/',route=>route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({detail:'expired'})}));
 await boot(page,'/?page=tasks');

 await expect(page.getByText('Sitzung abgelaufen',{exact:true})).toBeVisible();
 await expect(page.getByText(/Danach geht es im gleichen Bereich weiter/)).toBeVisible();
 await expect(page.locator('.toast')).toHaveCount(0);
 await expect(page).toHaveURL(/\?page=tasks$/);

 await page.getByLabel('Benutzername').fill('alex');
 await page.getByLabel('Passwort').fill('secret');
 await page.getByRole('button',{name:'Anmelden',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Aufgaben',exact:true})).toBeVisible();
 await expect(page.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=tasks$/);
});
