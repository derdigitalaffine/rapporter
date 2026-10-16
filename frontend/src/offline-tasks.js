import {offlineIdentity,readyOfflineEngine} from './offline-runtime.js';
const day=(value,zone)=>{if(!value)return '';const parts=new Intl.DateTimeFormat('en',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));return ['year','month','day'].map(type=>parts.find(p=>p.type===type).value).join('-')};
export async function projectLocalTasks(engine,family){
 const lists=await engine.list('task_list'),today=day(new Date(),family.timezone||'UTC');
 const projection=(await engine.store.get('meta','projections'))?.data?.actions||[];
 const result=[];
 for(const task of await engine.list('task')){
  const original=projection.find(a=>a.id===`task:${task.id}`)||{};
  const list=lists.find(l=>l.id===task.task_list),column=list?.workflow_columns?.find(c=>c.id===task.workflow_column);
  const due=day(task.due_at,family.timezone||'UTC'),done=day(task.completed_at,family.timezone||'UTC');
  const state=task.completed_at?(done===today?'done_today':'done'):due&&due<today?'overdue':due===today?'due':column?.kind==='active'?'active':column?.kind==='waiting'?'waiting':'open';
  const toggle={id:task.completed_at?'reopen':'complete',method:'POST',href:`/api/tasks/${task.id}/toggle/`};
  result.push({...original,id:`task:${task.id}`,family:engine.familyId,kind:'task',title:task.title,state,due_at:task.due_at,next_due_at:task.completed_at?null:task.due_at,completed_at:task.completed_at,
   assignee:task.assignee?{id:task.assignee,username:task.assignee_name||''}:null,priority:task.priority||'normal',tags:task.tags||[],repeat:task.recurrence?{recurrence:task.recurrence}:null,
   primary_action:toggle,completion_command:null,allowed_actions:[toggle,{id:'edit',method:'PATCH',href:`/api/tasks/${task.id}/`},{id:'delete',method:'DELETE',href:`/api/tasks/${task.id}/`}],
   deep_link:`/?page=tasks&family=${engine.familyId}&task=${task.id}`,context:{source:task.source||'manual',list:list?{id:list.id,name:list.name}:null,workflow:column?{id:column.id,name:column.name,kind:column.kind,terminal:column.is_terminal}:null},
   schedule:task.action_schedule||original.schedule,
   urgency:state==='overdue'?'critical':['due','active','waiting'].includes(state)||task.priority==='high'?'high':task.completed_at?'none':'normal',_offlinePending:task._offlinePending});
 }
 // Routines keep their canonical read projection; their writes remain owned by
 // the existing Routine service and are outside the agreed Task sync entities.
 return [...result,...projection.filter(a=>a.kind!=='task')];
}
export async function offlineTaskRequest(path,options={}){
 const identity=offlineIdentity();if(!identity)return {handled:false};
 const url=new URL(path,'https://local.invalid'),route=url.pathname,method=(options.method||'GET').toUpperCase();
 if(!/^\/(tasks|task-lists|smart\/tasks\/|actions\/)/.test(route))return {handled:false};
 let data={};if(options.body){try{data=JSON.parse(options.body)}catch{return {handled:false}}}
 const familyId=String(data.family||url.searchParams.get('family')||localStorage.getItem('famuhle-active-family')||identity.families?.[0]?.id||'');
 const e=await readyOfflineEngine(familyId),family=identity.families?.find(f=>String(f.id)===familyId)||{};
 const match=route.match(/^\/(tasks|task-lists)\/(?:([^/]+)\/)?$/);
 if(match){
  const kind=match[1]==='tasks'?'task':'task_list',id=match[2];if(id==='suggestions')return {handled:true,value:[]};
  if(method==='GET'){
   let rows=await e.list(kind);
   if(kind==='task_list'){const tasks=await e.list('task');rows=rows.map(l=>({...l,workflow_columns:l.workflow_columns||[],open_count:tasks.filter(t=>t.task_list===l.id&&!t.completed_at).length,done_count:tasks.filter(t=>t.task_list===l.id&&t.completed_at).length}))}
   return {handled:true,value:id?rows.find(r=>r.id===id):rows};
  }
  if(['POST','PATCH','PUT','DELETE'].includes(method)){
   if(method==='POST')data={family:familyId,...data};
   return {handled:true,value:await e.mutate(kind,id,method==='POST'?'create':method==='DELETE'?'delete':'update',data)};
  }
 }
 if(route==='/smart/tasks/quick-add/'&&method==='POST'){
  let list=data.task_list;if(!list)list=(await e.list('task_list')).find(l=>!l.archived)?.id;
  if(!list)list=(await e.mutate('task_list',null,'create',{family:familyId,name:family.locale==='en'?'General':'Allgemein',icon:'list-check'})).id;
  const title=String(data.title||data.name||'').trim();if(!title)throw new Error('task_title_required');
  const existing=(await e.list('task')).find(t=>t.task_list===list&&!t.completed_at&&!t.birthday_context&&String(t.title).toLocaleLowerCase()===title.toLocaleLowerCase());
  const values={};for(const key of ['notes','priority','estimate_minutes','recurrence','tags','due_at','assignee'])if(data[key]!==undefined&&data[key]!==null&&data[key]!=='')values[key]=data[key];
  const task=await e.mutate('task',existing?.id,existing?'update':'create',existing?values:{...values,title,family:familyId,task_list:list});
  return {handled:true,value:{task,reused:Boolean(existing)}};
 }
 const toggle=route.match(/^\/tasks\/([^/]+)\/toggle\/$/),move=route.match(/^\/tasks\/([^/]+)\/move\/$/);
 if(method==='POST'&&(toggle||move)){
  const id=(toggle||move)[1],task=await e.get('task',id);if(!task)throw new Error('task_unavailable');
  const command=move?'move_task':data.operation==='complete'?'complete_task':data.operation==='reopen'?'reopen_task':task.completed_at?'reopen_task':'complete_task';
  if(move){const list=await e.get('task_list',task.task_list),column=list?.workflow_columns?.find(c=>c.id===data.column_id);if(!column)throw new Error('workflow_column_unavailable');data.local_terminal=Boolean(column.is_terminal)}
  return {handled:true,value:await e.mutate('task',id,'command',{command,args:data})};
 }
 if(route==='/actions/execute/'&&method==='POST'&&String(data.action_id).startsWith('task:')){
  if(data.operation==='undo')throw new Error('Use reopen for an offline task completion.');
  const id=data.action_id.slice(5);return {handled:true,value:await e.mutate('task',id,'command',{command:data.operation==='reopen'?'reopen_task':'complete_task',args:{duration_minutes:data.duration_minutes}})};
 }
 if(route==='/actions/'&&method==='GET'){
  const all=await projectLocalTasks(e,family),scope=url.searchParams.get('scope')||'today';
  const today=day(new Date(),family.timezone||'UTC');
  const actions=all.filter(a=>{
   if(url.searchParams.get('kind')==='tasks'&&a.kind!=='task'||url.searchParams.get('kind')==='routines'&&a.kind!=='routine')return false;
   if(url.searchParams.get('task')&&a.id!==`task:${url.searchParams.get('task')}`)return false;
   if(url.searchParams.get('list')&&a.context?.list?.id!==url.searchParams.get('list'))return false;
   if(scope==='completed'||scope==='recent')return ['done','done_today'].includes(a.state);
   if(a.kind!=='task')return scope==='all'||(scope==='upcoming'?!['done','done_today'].includes(a.state):a.state!=='done');
   if(scope==='mine')return String(a.assignee?.id)===String(identity.session.user.id)&&!a.completed_at;
   if(scope==='upcoming')return !a.completed_at&&a.due_at&&day(a.due_at,family.timezone||'UTC')>today;
   if(scope==='today')return ['overdue','due','active','waiting','done_today'].includes(a.state)||Boolean(a.schedule?.recurrence);
   return a.state!=='done';
  });
  return {handled:true,value:{actions,results:actions,focus:[],next:null,count:actions.length}};
 }
 const detail=route.match(/^\/actions\/task\/([^/]+)\/$/);
 if(detail&&method==='GET'){const action=(await projectLocalTasks(e,family)).find(a=>a.id===`task:${detail[1]}`);if(!action)throw new Error('task_unavailable');return {handled:true,value:{id:action.canonical_action_id||'',action_id:action.id,schedule:action.schedule||{},prediction:action.prediction_v2||null,decision_templates:[]}}}
 const columns=route.match(/^\/task-lists\/([^/]+)\/workflow-columns\/$/);
 if(columns&&method==='GET')return {handled:true,value:(await e.get('task_list',columns[1]))?.workflow_columns||[]};
 return {handled:false};
}
