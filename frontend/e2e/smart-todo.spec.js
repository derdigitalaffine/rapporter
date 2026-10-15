import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const familyId='family-1';
function row(id,title,state='due',reasons=['due_today']){return{id:`task:${id}`,family:familyId,kind:'task',title,state,due_at:new Date().toISOString(),next_due_at:new Date().toISOString(),completed_at:null,assignee:null,priority:'normal',urgency:state==='overdue'?'critical':'high',context:{source:'manual',list:{id:'tasks-1',name:'Alltag'},workflow:null},repeat:null,tags:[],primary_action:{id:'complete',method:'POST',href:`/api/tasks/${id}/toggle/`},allowed_actions:[],deep_link:`/?page=tasks&task=${id}`,ranking:{version:'actions-v1',bucket:state==='overdue'?0:1,reasons},smart:{pinned:false,hidden_from_focus:false,reasons,version:'todo-focus-v1'}}}

async function installSmartMocks(page){
 const state={smart:true,sort:'smart',pinned:new Set(),hidden:new Set(),gets:0,actions:[row('overdue','Steuerbrief','overdue',['overdue']),row('due','Sporttasche','due',['due_today'])]};
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),method=request.method(),path=url.pathname.replace(/^\/api/,'');
  if(path==='/actions/'&&method==='GET'){
   state.gets++;
   const decorated=state.actions.map(item=>({...item,smart:{...item.smart,pinned:state.pinned.has(item.id),hidden_from_focus:state.hidden.has(item.id),reasons:[...(state.pinned.has(item.id)?['pinned']:[]),...(item.state==='overdue'?['overdue']:['due_today'])]}}));
   let focus=state.smart?decorated.filter(item=>!state.hidden.has(item.id)):[];
   focus.sort((a,b)=>(state.pinned.has(a.id)?0:1)-(state.pinned.has(b.id)?0:1));
   if(state.gets>1&&!state.pinned.size&&!state.hidden.size)focus=[...focus].reverse();
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:decorated.length,next:null,previous:null,results:decorated,focus,preferences:{smart_ranking_enabled:state.smart,today_sort:state.sort,pinned_action_ids:[...state.pinned],hidden_focus_action_ids:[...state.hidden]},ranking_version:'actions-v1',focus_ranking_version:'todo-focus-v1',scope:'today'})});
  }
  if(path==='/actions/'&&method==='PATCH'){
   const body=request.postDataJSON()||{};
   if(body.reset){state.smart=true;state.sort='smart';state.pinned.clear();state.hidden.clear()}
   if(typeof body.smart_ranking_enabled==='boolean')state.smart=body.smart_ranking_enabled;
   if(body.today_sort)state.sort=body.today_sort;
   if(body.action_id&&typeof body.pinned==='boolean'){body.pinned?state.pinned.add(body.action_id):state.pinned.delete(body.action_id)}
   if(body.action_id&&typeof body.hidden_from_focus==='boolean'){body.hidden_from_focus?state.hidden.add(body.action_id):state.hidden.delete(body.action_id)}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({smart_ranking_enabled:state.smart,today_sort:state.sort,pinned_action_ids:[...state.pinned],hidden_focus_action_ids:[...state.hidden]})});
  }
  if(/^\/tasks\/[^/]+\/toggle\/$/.test(path)&&method==='POST')return route.fulfill({status:200,contentType:'application/json',body:'{}'});
  return route.fallback();
 });
 return state;
}

async function boot(page){
 await installApiMocks(page,{dismissOnboarding:true});
 const state=await installSmartMocks(page);
 await page.goto('/?page=todo');
 await page.waitForLoadState('networkidle');
 await expect(page.getByRole('heading',{name:'To-dos'})).toBeVisible();
 return state;
}

function todoTabs(page){return page.locator('nav[aria-label="To-dos"]')}
function focusItems(page){return page.locator('.todo-focus-item')}

test('today prioritizes focus, then creation, then recent activity capture',async({page})=>{
 await boot(page);
 const order=await page.locator('.todo-hub > .todo-focus, .todo-hub > .todo-quick, .todo-hub > .action-capture').evaluateAll(nodes=>nodes.map(node=>node.classList.contains('todo-focus')?'focus':node.classList.contains('todo-quick')?'quick':'capture'));
 expect(order).toEqual(['focus','quick','capture']);
 await expect(page.getByRole('heading',{name:'Als Nächstes'})).toBeVisible();
 await expect(page.locator('.todo-quick')).toContainText('Schnell hinzufügen');
 await expect(page.locator('.action-capture')).toContainText('Ich habe gerade');
});

test('focus explains suggestions and manual pin outranks canonical order',async({page})=>{
 await boot(page);
 await expect(page.getByRole('heading',{name:'Als Nächstes'})).toBeVisible();
 await expect(focusItems(page).nth(0)).toContainText('Überfällig');
 await focusItems(page).nth(1).getByRole('button',{name:'Anpinnen: Sporttasche'}).click();
 await expect(focusItems(page).nth(0)).toContainText('Sporttasche');
 await expect(focusItems(page).nth(0)).toContainText('Von dir angepinnt');
});

test('hiding a suggestion removes only focus while the canonical row remains',async({page})=>{
 await boot(page);
 await focusItems(page).nth(0).getByRole('button',{name:/Aus Fokus ausblenden:/}).click();
 await expect(focusItems(page).filter({hasText:'Steuerbrief'})).toHaveCount(0);
 await expect(page.locator('.todo-section').getByText('Steuerbrief',{exact:true})).toBeVisible();
});

test('smart ranking can be disabled and reset from More',async({page})=>{
 await boot(page);
 await todoTabs(page).getByRole('button',{name:'Mehr',exact:true}).click();
 const smart=page.getByLabel('Smart Ranking');await expect(smart).toBeChecked();await smart.uncheck();
 await todoTabs(page).getByRole('button',{name:'Heute',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Als Nächstes'})).toHaveCount(0);
 await todoTabs(page).getByRole('button',{name:'Mehr',exact:true}).click();
 await page.getByRole('button',{name:'Präferenzen zurücksetzen'}).click();
 await todoTabs(page).getByRole('button',{name:'Heute',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Als Nächstes'})).toBeVisible();
});

test('focus keeps survivor order across ordinary projection refreshes',async({page})=>{
 await boot(page);
 await expect(focusItems(page).nth(0)).toContainText('Steuerbrief');
 await focusItems(page).nth(0).getByRole('button',{name:'Erledigen: Steuerbrief'}).click();
 await expect(page.getByRole('button',{name:/Rückgängig/})).toBeVisible();
 await expect(focusItems(page).nth(0)).toContainText('Steuerbrief');
 await expect(focusItems(page).nth(1)).toContainText('Sporttasche');
});