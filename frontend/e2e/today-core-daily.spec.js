import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const familyId='family-1';
const isoIn=hours=>new Date(Date.now()+hours*3600000).toISOString();
function localDay(){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
 const read=type=>parts.find(part=>part.type===type)?.value||'';
 return `${read('year')}-${read('month')}-${read('day')}`;
}
function actionRows(state){
 return state.tasks.map(task=>({
  id:`task:${task.id}`,family:familyId,kind:'task',title:task.title,state:task.completed_at?'done_today':'due',due_at:task.due_at,next_due_at:task.completed_at?null:task.due_at,completed_at:task.completed_at,
  assignee:task.assignee?{id:task.assignee,username:task.assignee_name||'alex'}:null,priority:task.priority||'normal',urgency:task.completed_at?'none':'high',context:{source:'manual',list:{id:task.task_list,name:task.list_name},workflow:null},repeat:null,tags:[],
  primary_action:{id:task.completed_at?'reopen':'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`},allowed_actions:[{id:task.completed_at?'reopen':'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`},{id:'edit',method:'PATCH',href:`/api/tasks/${task.id}/`}],deep_link:`/?page=tasks&task=${task.id}`,ranking:{version:'actions-v1',bucket:task.completed_at?6:1,reasons:[task.completed_at?'done_today':'due_now']}
 }));
}
async function boot(page){
 await page.setViewportSize({width:390,height:844});
 const state=await installApiMocks(page,{dismissOnboarding:true});
 state.tasks[0].due_at=isoIn(2);
 state.events.push(
  {id:'warning-today',family:familyId,source:null,type:'public.warning',title:'Sturmwarnung',starts_at:isoIn(1),ends_at:isoIn(4),payload:{provider:'Warnamt'}},
  {id:'all-day',family:familyId,source:null,type:'calendar.event',title:'Schulfest',starts_at:null,ends_at:null,payload:{date_start:localDay(),date_end_exclusive:null,provider:'Familie'}}
 );
 let actionRequests=0;
 await page.route('**/api/actions/**',route=>{
  actionRequests+=1;const rows=actionRows(state);
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:rows.length,next:null,previous:null,results:rows,ranking_version:'actions-v1',scope:'today'})});
 });
 await page.goto('/');
 await expect(page.getByTestId('today-situation')).toBeVisible();
 await expect(page.getByTestId('today-focus')).toBeVisible();
 await expect(page.getByTestId('today-timeline')).toBeVisible();
 return {state,actionRequests:()=>actionRequests};
}

test('legacy priority and next migrate to canonical Focus and Timeline with one shared action read',async({page})=>{
 const {state,actionRequests}=await boot(page);
 await expect(page.getByTestId('today-situation')).toContainText('Ding heute offen');
 const focus=page.getByTestId('today-focus');
 await expect(focus).toContainText('Sturmwarnung');
 await expect(focus).toContainText('Wäsche aufhängen');
 expect(await focus.locator('ol > li').count()).toBeLessThanOrEqual(3);
 const timeline=page.getByTestId('today-timeline');
 await expect(timeline).toContainText('Schulfest');
 await expect(timeline).toContainText('Kinderarzt');
 await expect(timeline).toContainText('Wäsche aufhängen');
 await expect(timeline).not.toContainText('Sturmwarnung');
 await expect.poll(actionRequests).toBe(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);

 await page.getByRole('button',{name:'Anpassen'}).click();
 const editor=page.getByRole('region',{name:'Anpassen'});
 await expect(editor.locator('[data-editor-widget-id="focus"]')).toBeVisible();
 await expect(editor.locator('[data-editor-widget-id="timeline"]')).toBeVisible();
 await expect(editor.locator('[data-editor-widget-id="priority"]')).toHaveCount(0);
 await expect(editor.locator('[data-editor-widget-id="next"]')).toHaveCount(0);
 await editor.getByRole('button',{name:'Speichern',exact:true}).click();
 expect(state.todayLayout.version).toBe(2);
 expect(state.todayLayout.widgets.some(row=>row.id==='focus')).toBe(true);
 expect(state.todayLayout.widgets.some(row=>row.id==='timeline')).toBe(true);
 expect(state.todayLayout.widgets.some(row=>['priority','next'].includes(row.id))).toBe(false);
});

test('completing a shared Today action refreshes To-do, Focus, Timeline and Situation together',async({page})=>{
 const {actionRequests}=await boot(page);
 const focus=page.getByTestId('today-focus');const timeline=page.getByTestId('today-timeline');const todo=page.getByTestId('today-todos');
 await expect(focus.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
 await expect(timeline.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
 await expect.poll(actionRequests).toBe(1);
 await todo.getByRole('button',{name:'Erledigen: Wäsche aufhängen'}).click();
 await expect(todo.getByRole('button',{name:/Rückgängig/})).toBeFocused();
 await expect(focus.getByText('Wäsche aufhängen',{exact:true})).toHaveCount(0);
 await expect(timeline.getByText('Wäsche aufhängen',{exact:true})).toHaveCount(0);
 await expect(page.getByTestId('today-situation')).not.toContainText('Ding heute offen');
 await expect.poll(actionRequests).toBe(2);
});
