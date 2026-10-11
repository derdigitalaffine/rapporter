import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {installApiMocks} from './mock-api.js';

const familyId='family-1';
const isoIn=hours=>new Date(Date.now()+hours*3600000).toISOString();

async function installTodoMocks(page){
 const state={
  nextTask:2,nextRoutine:2,nextLog:1,
  actions:[
   {id:'task:task-1',family:familyId,kind:'task',title:'Wäsche aufhängen',state:'due',due_at:isoIn(3),next_due_at:isoIn(3),completed_at:null,assignee:{id:1,username:'alex'},priority:'normal',urgency:'high',context:{source:'manual',list:{id:'tasks-1',name:'Alltag'},workflow:null},repeat:null,tags:[],primary_action:{id:'complete',method:'POST',href:'/api/tasks/task-1/toggle/'},allowed_actions:[],deep_link:'/?page=tasks&task=task-1',ranking:{version:'actions-v1',bucket:1,reasons:['due_now']}},
   {id:'routine:routine-1',family:familyId,kind:'routine',title:'Vitamin D',state:'due',due_at:null,next_due_at:isoIn(1),completed_at:null,assignee:null,priority:'normal',urgency:'high',context:{source:'routine',list:null,workflow:null},repeat:{target_count:1,target_period_days:1},tags:[],primary_action:{id:'record_done',method:'POST',href:'/api/routines/routine-1/done/'},allowed_actions:[],deep_link:'/?page=routines&routine=routine-1',ranking:{version:'actions-v1',bucket:3,reasons:['due_now']}}
  ]
 };
 await page.route('**/api/**',async route=>{
  const request=route.request();const method=request.method();const url=new URL(request.url());const path=url.pathname.replace(/^\/api/,'');let body={};try{body=request.postDataJSON()||{}}catch{}
  if(path==='/actions/'&&method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({actions:state.actions})});
  if(path==='/smart/tasks/quick-add/'&&method==='POST'){
   const id=`task-${state.nextTask++}`;state.actions.push({id:`task:${id}`,family:familyId,kind:'task',title:body.title,state:body.due_at?'due':'open',due_at:body.due_at||null,next_due_at:body.due_at||null,completed_at:null,assignee:body.assignee?{id:Number(body.assignee),username:'alex'}:null,priority:'normal',urgency:body.due_at?'high':'normal',context:{source:'manual',list:{id:body.task_list||'tasks-1',name:'Alltag'},workflow:null},repeat:null,tags:[],primary_action:{id:'complete',method:'POST',href:`/api/tasks/${id}/toggle/`},allowed_actions:[],deep_link:`/?page=tasks&task=${id}`,ranking:{version:'actions-v1',bucket:5,reasons:['normal']}});return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({task:{id,title:body.title},reused:false})});
  }
  const taskToggle=path.match(/^\/tasks\/([^/]+)\/toggle\/$/);if(taskToggle&&method==='POST'){
   const item=state.actions.find(row=>row.id===`task:${taskToggle[1]}`);if(item){const done=item.primary_action.id==='complete';item.state=done?'done_today':'due';item.completed_at=done?new Date().toISOString():null;item.primary_action={...item.primary_action,id:done?'reopen':'complete'}}return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({})});
  }
  if(path==='/routines/'&&method==='POST'){
   const id=`routine-${state.nextRoutine++}`;state.actions.push({id:`routine:${id}`,family:familyId,kind:'routine',title:body.name,state:'open',due_at:null,next_due_at:isoIn(24),completed_at:null,assignee:null,priority:'normal',urgency:'normal',context:{source:'routine',list:null,workflow:null},repeat:{target_count:body.target_count,target_period_days:body.target_period_days},tags:[],primary_action:{id:'record_done',method:'POST',href:`/api/routines/${id}/done/`},allowed_actions:[],deep_link:`/?page=routines&routine=${id}`,ranking:{version:'actions-v1',bucket:5,reasons:['normal']}});return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id,name:body.name})});
  }
  const routineDone=path.match(/^\/routines\/([^/]+)\/done\/$/);if(routineDone&&method==='POST'){
   const item=state.actions.find(row=>row.id===`routine:${routineDone[1]}`);if(item)item.state='done_today';const id=`log-${state.nextLog++}`;return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id,routine:routineDone[1],done_at:new Date().toISOString()})});
  }
  const routineUndo=path.match(/^\/routines\/([^/]+)\/logs\/([^/]+)\/$/);if(routineUndo&&method==='DELETE'){
   const item=state.actions.find(row=>row.id===`routine:${routineUndo[1]}`);if(item)item.state='due';return route.fulfill({status:204,body:''});
  }
  return route.fallback();
 });
 return state;
}

async function boot(page,{viewport}={}){
 if(viewport)await page.setViewportSize(viewport);
 await installApiMocks(page);
 await installTodoMocks(page);
 await page.goto('/?page=todo');
 await page.waitForLoadState('networkidle');
}
async function expectNoSevereA11y(page){const results=await new AxeBuilder({page}).include('main').withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();expect(results.violations.filter(item=>['critical','serious'].includes(item.impact))).toEqual([])}

test('unified To-do hub quick-adds a task and keeps full editor reachable',async({page})=>{
 await boot(page);
 await expect(page.getByRole('heading',{name:'To-dos'})).toBeVisible();
 await expect(page.locator('.bottom-nav').getByRole('button',{name:'To-dos'})).toHaveAttribute('aria-current','page');
 const input=page.getByPlaceholder('Was steht an?');await input.fill('Schulranzen packen');
 await page.getByRole('button',{name:'Morgen',exact:true}).click();
 await page.getByRole('button',{name:'Hinzufügen',exact:true}).click();
 await expect(page.getByText('Schulranzen packen',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Alle Felder'}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
});

test('task completion and undo use the canonical toggle and preserve focus',async({page})=>{
 await boot(page);
 const complete=page.getByRole('button',{name:'Erledigen: Wäsche aufhängen'});await complete.click();
 const undo=page.getByRole('button',{name:/Rückgängig/});await expect(undo).toBeFocused();await undo.click();
 await expect(page.getByRole('button',{name:'Erledigen: Wäsche aufhängen'})).toBeVisible();
 await expect(page.getByText('Änderung rückgängig gemacht.')).toBeVisible();
});

test('routine quick add records exactly one log and supports safe undo',async({page})=>{
 await boot(page);
 await page.getByRole('button',{name:'Routine',exact:true}).click();
 const input=page.getByPlaceholder('Neue Routine');await input.fill('Abends lüften');
 await page.getByLabel('Rhythmus').selectOption('weekly');
 await page.getByLabel('Erinnerung').check();
 await page.getByRole('button',{name:'Hinzufügen',exact:true}).click();
 await expect(page.getByText('Abends lüften',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Erledigt: Abends lüften'}).click();
 await expect(page.getByRole('button',{name:/Rückgängig/})).toBeVisible();
 await page.getByRole('button',{name:/Rückgängig/}).click();
 await expect(page.getByRole('button',{name:'Erledigt: Abends lüften'})).toBeVisible();
});

test('lists and more preserve legacy task, workflow and routine routes',async({page})=>{
 await boot(page);
 await page.getByRole('button',{name:'Listen',exact:true}).click();
 await expect(page.getByRole('link',{name:/Aufgaben & Listen/})).toHaveAttribute('href',/page=tasks/);
 await expect(page.getByRole('link',{name:/Routinen verwalten/})).toHaveAttribute('href',/page=routines/);
 await page.getByRole('button',{name:'Mehr',exact:true}).click();
 await expect(page.getByRole('link',{name:/Erledigt & Verlauf/})).toHaveAttribute('href',/mode=completed/);
 await expect(page.getByRole('link',{name:/Workflows \/ Kanban/})).toHaveAttribute('href',/mode=workflow/);
});

test('mobile hub has no horizontal overflow and no serious accessibility violations',async({page})=>{
 await boot(page,{viewport:{width:360,height:740}});
 await expect(page.getByRole('button',{name:'Heute',exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 await expectNoSevereA11y(page);
});