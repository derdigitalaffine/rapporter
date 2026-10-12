import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const legacyIds=['weather','priority','waste','next','tasks','shopping','routines','birthdays','notes'];
const familyId='family-1';
const isoIn=hours=>new Date(Date.now()+hours*3600000).toISOString();

function actionRows(state){
 const tasks=state.tasks.map(task=>({
  id:`task:${task.id}`,family:familyId,kind:'task',title:task.title,state:task.completed_at?'done_today':'due',due_at:task.due_at||null,next_due_at:task.completed_at?null:(task.due_at||null),completed_at:task.completed_at||null,
  assignee:task.assignee?{id:task.assignee,username:task.assignee_name||'alex'}:null,priority:task.priority||'normal',urgency:'high',context:{source:'manual',list:{id:task.task_list||'tasks-1',name:task.list_name||'Alltag'},workflow:null},repeat:null,tags:[],
  primary_action:{id:task.completed_at?'reopen':'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`},
  allowed_actions:[{id:task.completed_at?'reopen':'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`},{id:'edit',method:'PATCH',href:`/api/tasks/${task.id}/`}],
  deep_link:`/?page=tasks&task=${task.id}`,ranking:{version:'actions-v1',bucket:1,reasons:['due_now']}
 }));
 const routines=state.routines.map(routine=>({
  id:`routine:${routine.id}`,family:familyId,kind:'routine',title:routine.name,state:routine.__doneToday?'done_today':'due',due_at:null,next_due_at:routine.prediction?.expected_at||isoIn(1),completed_at:null,assignee:null,priority:'normal',urgency:'high',context:{source:'routine',list:null,workflow:null},repeat:{target_count:1,target_period_days:1},tags:[],
  primary_action:{id:'record_done',method:'POST',href:`/api/routines/${routine.id}/done/`},
  allowed_actions:[{id:'record_done',method:'POST',href:`/api/routines/${routine.id}/done/`},{id:'snooze',method:'POST',href:`/api/routines/${routine.id}/snooze/`},{id:'edit',method:'PATCH',href:`/api/routines/${routine.id}/`}],
  deep_link:`/?page=routines&routine=${routine.id}`,ranking:{version:'actions-v1',bucket:3,reasons:['due_now']}
 }));
 return [...tasks,...routines];
}

async function boot(page,{language='de',failSave=false,conflict=false,routines=[]}={}){
 const state=await installApiMocks(page,{language});state.routines=routines;state.actionRequests=[];state.snoozes=[];state.nextLog=1;
 let layout={version:1,revision:0,widgets:legacyIds.map(id=>({id,visible:true,size:id==='routines'?'square':'full'}))};
 await page.route('**/api/today-layout/**',async route=>{
  const method=route.request().method();
  if(method==='PUT'){
   if(failSave)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Unavailable'})});
   if(conflict)return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Layout changed on another device.'})});
   layout={...route.request().postDataJSON(),revision:layout.revision+1};
  }
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(layout)});
 });
 await page.route('**/api/actions/**',async route=>{
  const url=new URL(route.request().url());const family=url.searchParams.get('family');const scope=url.searchParams.get('scope');state.actionRequests.push({family,scope});
  if(family!==familyId)return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({detail:'family'})});
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:actionRows(state).length,next:null,previous:null,results:actionRows(state),ranking_version:'actions-v1',scope})});
 });
 await page.route('**/api/routines/**',async route=>{
  const request=route.request();const path=new URL(request.url()).pathname.replace(/^\/api/,'');let body={};try{body=request.postDataJSON()||{}}catch{}
  const done=path.match(/^\/routines\/([^/]+)\/done\/$/);if(done&&request.method()==='POST'){
   const routine=state.routines.find(row=>String(row.id)===done[1]);if(routine)routine.__doneToday=true;const id=`log-${state.nextLog++}`;return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id,routine:done[1],done_at:new Date().toISOString()})});
  }
  const undo=path.match(/^\/routines\/([^/]+)\/logs\/([^/]+)\/$/);if(undo&&request.method()==='DELETE'){
   const routine=state.routines.find(row=>String(row.id)===undo[1]);if(routine)routine.__doneToday=false;return route.fulfill({status:204,body:''});
  }
  const snooze=path.match(/^\/routines\/([^/]+)\/snooze\/$/);if(snooze&&request.method()==='POST'){
   state.snoozes.push({id:snooze[1],hours:body.hours});return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({snoozed_until:isoIn(body.hours||24)})});
  }
  return route.fallback();
 });
 await page.goto('/');await expect(page.getByRole('button',{name:language==='de'?'Anpassen':'Customize'})).toBeEnabled();
 return {state,getLayout:()=>layout};
}

const editorRow=(editor,id)=>editor.locator(`[data-editor-widget-id="${id}"]`);

async function hideFromEditor(editor,id,label='Ausblenden'){
 const row=editorRow(editor,id);
 await expect(row).toBeVisible();
 await row.getByRole('button',{name:label,exact:true}).click();
 await expect(row).toHaveCount(0);
}

test('legacy split layout consolidates to one Today To-do widget and saves canonically',async({page})=>{
 const {getLayout}=await boot(page);await expect(page.locator('[data-today-widget="todo"]')).toBeVisible();await expect(page.locator('[data-today-widget="tasks"]')).toHaveCount(0);await expect(page.locator('[data-today-widget="routines"]')).toHaveCount(0);
 await page.getByRole('button',{name:'Anpassen'}).click();const editor=page.getByRole('region',{name:'Anpassen'});await expect(editorRow(editor,'todo')).toBeVisible();await expect(editorRow(editor,'tasks')).toHaveCount(0);await expect(editorRow(editor,'routines')).toHaveCount(0);
 await hideFromEditor(editor,'todo');await expect(page.locator('[data-today-widget="todo"]')).toHaveCount(0);await editor.getByRole('button',{name:'Abbrechen',exact:true}).click();await expect(page.locator('[data-today-widget="todo"]')).toBeVisible();
 await page.getByRole('button',{name:'Anpassen'}).click();await hideFromEditor(editor,'todo');await editor.getByRole('button',{name:'Speichern',exact:true}).click();expect(getLayout().widgets.some(row=>row.id==='todo')).toBe(true);expect(getLayout().widgets.some(row=>['tasks','routines'].includes(row.id))).toBe(false);
 await page.reload();await expect(page.locator('[data-today-widget="todo"]')).toHaveCount(0);
 await page.getByRole('button',{name:'Anpassen'}).click();await editor.getByRole('button',{name:'Standard wiederherstellen'}).click();await editor.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.locator('[data-today-widget="todo"]')).toBeVisible();
});

test('consolidated Today widget mixes tasks and routines with canonical family scope',async({page})=>{
 const {state}=await boot(page,{routines:[{id:'routine-1',family:familyId,name:'Spülmaschine',active:true,prediction:{status:'learning'}}]});const widget=page.getByTestId('today-todos');await expect(widget).toBeVisible();await expect(widget.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();await expect(widget.getByText('Spülmaschine',{exact:true})).toBeVisible();expect(state.actionRequests[0]).toEqual({family:familyId,scope:'today'});await expect(widget.getByRole('link',{name:/Alle To-dos/})).toHaveAttribute('href','/?page=todo');
});

test('Today task and routine primary actions are one click and undoable',async({page})=>{
 await boot(page,{routines:[{id:'routine-1',family:familyId,name:'Spülmaschine',active:true,prediction:{status:'due'}}]});const widget=page.getByTestId('today-todos');
 await widget.getByRole('button',{name:'Erledigen: Wäsche aufhängen'}).click();let undo=widget.getByRole('button',{name:/Rückgängig/});await expect(undo).toBeFocused();await undo.click();await expect(widget.getByRole('button',{name:'Erledigen: Wäsche aufhängen'})).toBeVisible();
 await widget.getByRole('button',{name:'Erledigt: Spülmaschine'}).click();undo=widget.getByRole('button',{name:/Rückgängig/});await expect(undo).toBeFocused();await undo.click();await expect(widget.getByRole('button',{name:'Erledigt: Spülmaschine'})).toBeVisible();
});

test('Today routine snooze is a two-click allowed quick action',async({page})=>{
 const {state}=await boot(page,{routines:[{id:'routine-1',family:familyId,name:'Spülmaschine',active:true,prediction:{status:'due'}}]});const widget=page.getByTestId('today-todos');const menu=widget.locator('summary[aria-label="Schnellaktionen: Spülmaschine"]');await menu.click();await widget.getByRole('button',{name:'24 Std. pausieren'}).click();await expect.poll(()=>state.snoozes).toEqual([{id:'routine-1',hours:24}]);await expect(widget.getByText('Routine für 24 Stunden pausiert.',{exact:true})).toBeVisible();await expect(menu).toBeFocused();
});

test('core widgets expose semantic medium sizes without legacy square values',async({page})=>{
 await boot(page);await page.getByRole('button',{name:'Anpassen'}).click();const editor=page.getByRole('region',{name:'Anpassen'});
 const todoSize=editor.getByRole('combobox',{name:'To-dos · Größe'});await expect(todoSize.locator('option[value="medium"]')).toHaveCount(1);await expect(todoSize.locator('option[value="square"]')).toHaveCount(0);await todoSize.selectOption('medium');await expect(todoSize).toHaveValue('medium');
 const weekSize=editor.getByRole('combobox',{name:'Wochenkompass · Größe'});await expect(weekSize.locator('option[value="medium"]')).toHaveCount(1);
 const focusSize=editor.getByRole('combobox',{name:'Jetzt wichtig · Größe'});await expect(focusSize.locator('option[value="medium"]')).toHaveCount(0);await expect(focusSize.locator('option[value="square"]')).toHaveCount(0);
});

test('failed save preserves draft and concurrent edits require reload',async({page})=>{
 await boot(page,{conflict:true});await page.getByRole('button',{name:'Anpassen'}).click();const editor=page.getByRole('region',{name:'Anpassen'});await hideFromEditor(editor,'shopping');await editor.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.getByRole('alert')).toContainText('anderen Gerät');await expect(editor).toBeVisible();await expect(editor.getByRole('button',{name:'Speichern',exact:true})).toBeDisabled();await expect(editor.locator('[data-library-widget="shopping"]')).toBeVisible();await page.getByRole('button',{name:'Erneut laden'}).click();await expect(editor).toHaveCount(0);
});

test('English grid editor fits narrow view and is keyboard operable',async({page})=>{
 await page.setViewportSize({width:360,height:800});await boot(page,{language:'en'});await page.getByRole('button',{name:'Customize'}).click();const editor=page.getByRole('region',{name:'Customize'});const hide=editorRow(editor,'todo').getByRole('button',{name:'Hide',exact:true});await hide.focus();await page.keyboard.press('Enter');await expect(editorRow(editor,'todo')).toHaveCount(0);await expect(editor.locator('[data-library-widget="todo"]')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await editor.getByRole('button',{name:'Cancel',exact:true}).click();await expect(page.locator('[data-today-widget="todo"]')).toBeVisible();
});

test('temporary save error keeps edited visibility for retry',async({page})=>{
 await boot(page,{failSave:true});await page.getByRole('button',{name:'Anpassen'}).click();const editor=page.getByRole('region',{name:'Anpassen'});await hideFromEditor(editor,'shopping');await editor.getByRole('button',{name:'Speichern',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Entwurf bleibt erhalten');await expect(editor.locator('[data-library-widget="shopping"]')).toBeVisible();await expect(editor.getByRole('button',{name:'Speichern',exact:true})).toBeEnabled();
});

test('Today To-do quick actions fit 390px without horizontal overflow',async({page})=>{
 await page.setViewportSize({width:390,height:780});await boot(page,{routines:[{id:'routine-1',family:familyId,name:'Spülmaschine',active:true,prediction:{status:'due'}}]});const widget=page.getByTestId('today-todos');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);for(const locator of [widget.getByRole('button',{name:'Erledigen: Wäsche aufhängen'}),widget.locator('summary[aria-label="Schnellaktionen: Spülmaschine"]')]){const box=await locator.boundingBox();expect(box?.width).toBeGreaterThanOrEqual(44);expect(box?.height).toBeGreaterThanOrEqual(44)}
});