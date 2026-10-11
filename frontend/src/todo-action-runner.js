import {api} from './api';

export function actionApiPath(href){
  const url=new URL(href,location.origin);
  const pathname=url.pathname.startsWith('/api/')?url.pathname.slice(4):url.pathname;
  return `${pathname}${url.search}`;
}

function requestId(){
  return crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function body(payload){
  return payload===undefined?undefined:JSON.stringify(payload);
}

export async function runTodoPrimary(item){
  const action=item?.primary_action||{};
  const endpoint=action.href?actionApiPath(action.href):'';
  if(!endpoint)throw new Error('todo_action_missing');

  if(item.kind==='task'&&['complete','reopen'].includes(action.id)&&action.method==='POST'){
    await api(endpoint,{method:'POST'});
    return {undo:()=>api(endpoint,{method:'POST'})};
  }

  if(item.kind==='routine'&&action.id==='record_done'&&action.method==='POST'){
    const log=await api(endpoint,{method:'POST',body:body({request_id:requestId()})});
    if(!log?.id)throw new Error('routine_log_missing');
    const routineId=String(item.id||'').split(':')[1];
    if(!routineId)throw new Error('routine_id_missing');
    return {undo:()=>api(`/routines/${routineId}/logs/${log.id}/`,{method:'DELETE'})};
  }

  if(item.kind==='routine'&&action.id==='reactivate'&&action.method==='PATCH'){
    await api(endpoint,{method:'PATCH',body:body(action.payload||{active:true})});
    return {undo:()=>api(endpoint,{method:'PATCH',body:body({active:false})})};
  }

  throw new Error('todo_action_not_supported');
}

function isAllowed(item,action){
  return (item?.allowed_actions||[]).some(candidate=>
    candidate?.id===action?.id&&candidate?.method===action?.method&&candidate?.href===action?.href
  );
}

export async function runTodoSecondary(item,action){
  if(!isAllowed(item,action))throw new Error('todo_action_not_allowed');
  if(item.kind==='routine'&&action.id==='snooze'&&action.method==='POST'){
    await api(actionApiPath(action.href),{method:'POST',body:body({hours:24})});
    return {id:'snooze'};
  }
  throw new Error('todo_action_not_supported');
}
