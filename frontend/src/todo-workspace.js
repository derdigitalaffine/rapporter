export const TODO_VIEWS=new Set(['upcoming','today','all','lists','more']);
export const TODO_GROUP_MODES=new Set(['date','status','list','person','none']);
export const TODO_SORT_MODES=new Set(['due','priority','newest','oldest']);
export const TODO_DENSITIES=new Set(['compact','comfortable']);
export const DEFAULT_TODO_VIEW_PREFERENCES=Object.freeze({group:'date',sort:'due',density:'compact'});

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
  const paused=item.state==='paused';
  if(['upcoming','today'].includes(view)&&(done||paused))return false;
  if(view==='all'&&!completed&&done)return false;
  if(view==='all'&&completed&&!done)return false;
  if(recurring&&item.kind!=='routine'&&!item.schedule?.recurrence)return false;
  if(term&&!item.title.toLocaleLowerCase().includes(term))return false;
  if(list&&String(item.context?.list?.id)!==String(list))return false;
  if(person&&String(item.assignee?.id)!==String(person))return false;
  return true;
 });
}

export function normalizeTodoViewPreferences(value={}){
 return {
  group:TODO_GROUP_MODES.has(value?.group)?value.group:DEFAULT_TODO_VIEW_PREFERENCES.group,
  sort:TODO_SORT_MODES.has(value?.sort)?value.sort:DEFAULT_TODO_VIEW_PREFERENCES.sort,
  density:TODO_DENSITIES.has(value?.density)?value.density:DEFAULT_TODO_VIEW_PREFERENCES.density,
 };
}

export function actionDate(item){
 return item?.prediction_v2?.expected_at||item?.due_at||item?.next_due_at||null;
}

function timeOf(value){
 if(!value)return null;
 const time=new Date(value).getTime();
 return Number.isNaN(time)?null:time;
}
function actionTime(item){return timeOf(actionDate(item))}
function createdTime(item){return timeOf(item?.created_at)||timeOf(item?.updated_at)||actionTime(item)}
function priorityRank(item){
 const priority=String(item?.priority||item?.urgency||'normal').toLowerCase();
 return {urgent:0,critical:0,high:1,normal:2,medium:2,low:3,none:4}[priority]??2;
}
function stableCompare(a,b){
 const title=String(a?.title||'').localeCompare(String(b?.title||''),undefined,{sensitivity:'base'});
 return title||String(a?.id||'').localeCompare(String(b?.id||''));
}
function compareDue(a,b){
 const aTime=actionTime(a),bTime=actionTime(b);
 if(aTime!==bTime){if(aTime===null)return 1;if(bTime===null)return -1;return aTime-bTime}
 const priority=priorityRank(a)-priorityRank(b);
 return priority||stableCompare(a,b);
}

export function sortActions(actions,mode='due'){
 const normalized=TODO_SORT_MODES.has(mode)?mode:'due';
 return [...actions].sort((a,b)=>{
  if(normalized==='priority'){
   const priority=priorityRank(a)-priorityRank(b);
   return priority||compareDue(a,b);
  }
  if(normalized==='newest'||normalized==='oldest'){
   const aTime=createdTime(a),bTime=createdTime(b);
   if(aTime!==bTime){
    if(aTime===null)return 1;
    if(bTime===null)return -1;
    return normalized==='newest'?bTime-aTime:aTime-bTime;
   }
   return stableCompare(a,b);
  }
  return compareDue(a,b);
 });
}

function startOfDay(value){return new Date(value.getFullYear(),value.getMonth(),value.getDate())}
function addDays(value,days){const next=new Date(value);next.setDate(next.getDate()+days);return next}
function dateGroup(item,now){
 const time=actionTime(item);
 if(time===null)return 'undated';
 const today=startOfDay(now),tomorrow=addDays(today,1),dayAfterTomorrow=addDays(today,2);
 const mondayIndex=(today.getDay()+6)%7;
 const nextMonday=addDays(today,7-mondayIndex);
 if(item.state==='overdue'||time<today.getTime())return 'overdue';
 if(time<tomorrow.getTime())return 'today';
 if(time<dayAfterTomorrow.getTime())return 'tomorrow';
 if(time<nextMonday.getTime())return 'thisWeek';
 return 'later';
}
function statusGroup(item){
 if(['done','done_today'].includes(item.state))return 'completed';
 if(item.state==='overdue')return 'overdue';
 if(item.state==='due')return 'due';
 if(item.state==='active')return 'active';
 if(item.state==='waiting')return 'waiting';
 if(item.state==='paused')return 'paused';
 return 'open';
}

const DATE_ORDER=['overdue','today','tomorrow','thisWeek','later','undated'];
const STATUS_ORDER=['overdue','due','active','waiting','open','paused','completed'];
const DATE_LABELS={overdue:'overdue',today:'today',tomorrow:'tomorrow',thisWeek:'thisWeek',later:'later',undated:'undated'};
const STATUS_LABELS={overdue:'overdue',due:'due',active:'statusActive',waiting:'statusWaiting',open:'statusOpen',paused:'statusPaused',completed:'completed'};

function fixedGroups(items,keys,labelKeys,keyFor){
 const grouped=new Map(keys.map(key=>[key,[]]));
 for(const item of items){const key=keyFor(item);if(grouped.has(key))grouped.get(key).push(item)}
 return keys.filter(key=>grouped.get(key).length).map(key=>({key,labelKey:labelKeys[key],items:grouped.get(key)}));
}
function namedGroups(items,keyFor,labelFor,emptyKey,emptyLabelKey){
 const groups=new Map();
 for(const item of items){
  const rawKey=keyFor(item);const key=rawKey?String(rawKey):emptyKey;
  if(!groups.has(key))groups.set(key,{key,label:rawKey?labelFor(item):null,labelKey:rawKey?null:emptyLabelKey,items:[]});
  groups.get(key).items.push(item);
 }
 return [...groups.values()].sort((a,b)=>{
  if(a.key===emptyKey)return 1;if(b.key===emptyKey)return -1;
  return String(a.label||'').localeCompare(String(b.label||''),undefined,{sensitivity:'base'});
 });
}

export function groupActions(actions,{mode='date',sort='due',now=new Date()}={}){
 const normalizedMode=TODO_GROUP_MODES.has(mode)?mode:'date';
 const items=sortActions(actions,sort);
 if(normalizedMode==='none')return items.length?[{key:'all',labelKey:null,items}]:[];
 if(normalizedMode==='status')return fixedGroups(items,STATUS_ORDER,STATUS_LABELS,statusGroup);
 if(normalizedMode==='list')return namedGroups(items,item=>item.context?.list?.id,item=>item.context?.list?.name,'__none__','noList');
 if(normalizedMode==='person')return namedGroups(items,item=>item.assignee?.id,item=>item.assignee?.display_name||item.assignee?.username,'__none__','noPerson');
 return fixedGroups(items,DATE_ORDER,DATE_LABELS,item=>dateGroup(item,now));
}
