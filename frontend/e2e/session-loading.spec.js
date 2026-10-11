import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function boot(page,path='/'){
 await page.goto(path);
}

function actionFor(task){
 const primary={id:task.completed_at?'reopen':'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`};
 return {id:`task:${task.id}`,family:task.family,kind:'task',title:task.title,state:task.completed_at?'done_today':'open',due_at:task.due_at||null,next_due_at:task.due_at||null,completed_at:task.completed_at||null,assignee:task.assignee?{id:task.assignee,username:task.assignee_name}:null,priority:task.priority||'normal',urgency:'normal',context:{source:'manual',list:{id:task.task_list,name:task.list_name},workflow:null},repeat:null,tags:[],primary_action:primary,allowed_actions:[primary,{id:'edit',method:'PATCH',href:`/api/tasks/${task.id}/`}],deep_link:`/?page=tasks&task=${task.id}`,ranking:{version:'actions-v1',bucket:5,reasons:['normal']}};
}

test('initial dashboard shows loading instead of a false empty state',async({page})=>{
 const state=await installApiMocks(page,{language:'de'});
 state.tasks[0].due_at=null;
 await page.route('**/api/families/',async route=>{await sleep(700);await route.fallback()});
 await page.route('**/api/actions/**',route=>{const results=state.tasks.map(actionFor);return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:results.length,next:null,previous:null,results,ranking_version:'actions-v1',scope:'today'})})});
 await boot(page);
 await expect(page.getByText('Daten werden geladen …',{exact:true})).toBeVisible();
 await expect(page.getByText('Alles erledigt',{exact:true})).toHaveCount(0);
 await expect(page.getByTestId('today-todos').getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
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

 await page.getByLabel('E-Mail-Adresse').fill('alex@example.test');
 await page.getByLabel('Passwort').fill('secret');
 await page.getByRole('button',{name:'Anmelden',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Aufgaben',exact:true})).toBeVisible();
 await expect(page.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\?page=tasks$/);
});
