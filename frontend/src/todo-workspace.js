export const TODO_VIEWS=new Set(['upcoming','today','all','lists','more']);
export const isWorkView=view=>['upcoming','today','all'].includes(view);
export const scopeForView=(view,completed=false)=>view==='today'?'today':view==='all'&&completed?'completed':'all';
export function workspaceView(search,fallback='upcoming'){
 const params=new URLSearchParams(search);
 if(TODO_VIEWS.has(params.get('todo')))return params.get('todo');
 if(params.get('mode')==='completed')return 'all';
 if(params.get('mode')==='workflow'||params.has('list'))return 'lists';
 return fallback;
}
export function visibleActions(actions,{view='upcoming',query='',list='',person='',completed=false,recurring=false}={}){
 const term=query.trim().toLocaleLowerCase();
 return actions.filter(item=>{
  const done=['done','done_today'].includes(item.state);
  if(view==='upcoming'&&(done||item.state==='paused'))return false;
  if(view==='all'&&!completed&&done)return false;
  if(view==='all'&&completed&&!done)return false;
  if(recurring&&item.kind!=='routine'&&!item.schedule?.recurrence)return false;
  if(term&&!item.title.toLocaleLowerCase().includes(term))return false;
  if(list&&String(item.context?.list?.id)!==String(list))return false;
  if(person&&String(item.assignee?.id)!==String(person))return false;
  return true;
 });
}
