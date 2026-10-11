import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import './todo-hub.css';

const VIEWS=new Set(['today','upcoming','lists','more']);
const labels={
 de:{title:'To-dos',today:'Heute',upcoming:'Demnächst',lists:'Listen',more:'Mehr',quick:'Schnell hinzufügen',task:'Aufgabe',routine:'Routine',titlePlaceholder:'Was steht an?',routinePlaceholder:'Neue Routine',add:'Hinzufügen',adding:'Wird hinzugefügt…',todayChip:'Heute',tomorrow:'Morgen',person:'Person',list:'Liste',none:'Ohne',routinePreset:'Rhythmus',daily:'Täglich',weekly:'Wöchentlich',threeWeekly:'3× pro Woche',reminder:'Erinnerung',fullEditor:'Alle Felder',overdue:'Überfällig',dueToday:'Heute',routinesNow:'Routinen jetzt',inProgress:'In Arbeit / wartet',next:'Als Nächstes',doneToday:'Heute erledigt',empty:'Hier ist gerade nichts offen.',complete:'Erledigen',reopen:'Wieder öffnen',record:'Erledigt',undo:'Rückgängig',undone:'Änderung rückgängig gemacht.',saved:'Erledigt. Rückgängig ist möglich.',loadFailed:'To-dos konnten nicht geladen werden.',saveFailed:'Änderung konnte nicht gespeichert werden.',allTasks:'Aufgaben & Listen',allTasksHint:'Listen, Workflows und vollständige Aufgabendetails',allRoutines:'Routinen verwalten',allRoutinesHint:'Rhythmen, Erinnerungen und Verlauf',completed:'Erledigt & Verlauf',completedHint:'Abgeschlossene Aufgaben wiederfinden',workflows:'Workflows / Kanban',workflowsHint:'Statusspalten und Boards weiterverwenden',open:'Öffnen'},
 en:{title:'To-dos',today:'Today',upcoming:'Upcoming',lists:'Lists',more:'More',quick:'Quick add',task:'Task',routine:'Routine',titlePlaceholder:'What needs doing?',routinePlaceholder:'New routine',add:'Add',adding:'Adding…',todayChip:'Today',tomorrow:'Tomorrow',person:'Person',list:'List',none:'None',routinePreset:'Cadence',daily:'Daily',weekly:'Weekly',threeWeekly:'3× per week',reminder:'Reminder',fullEditor:'All fields',overdue:'Overdue',dueToday:'Today',routinesNow:'Routines now',inProgress:'In progress / waiting',next:'Up next',doneToday:'Done today',empty:'Nothing needs attention here.',complete:'Complete',reopen:'Reopen',record:'Done',undo:'Undo',undone:'Change undone.',saved:'Done. Undo is available.',loadFailed:'Could not load to-dos.',saveFailed:'Could not save the change.',allTasks:'Tasks & lists',allTasksHint:'Lists, workflows and full task details',allRoutines:'Manage routines',allRoutinesHint:'Cadence, reminders and history',completed:'Completed & history',completedHint:'Find completed tasks again',workflows:'Workflows / Kanban',workflowsHint:'Keep using status columns and boards',open:'Open'}
};

function apiPath(href){
 const url=new URL(href,location.origin);
 const pathname=url.pathname.startsWith('/api/')?url.pathname.slice(4):url.pathname;
 return `${pathname}${url.search}`;
}
function dueAt(day){
 const value=new Date();
 if(day==='tomorrow')value.setDate(value.getDate()+1);
 value.setHours(23,59,0,0);
 return value.toISOString();
}
function legacyHref(page,params={}){
 const url=new URL(location.href);
 url.searchParams.set('page',page);
 url.searchParams.delete('todo');
 for(const [key,value] of Object.entries(params)){
  if(value===null||value===undefined||value==='')url.searchParams.delete(key);else url.searchParams.set(key,String(value));
 }
 return `${url.pathname}${url.search}${url.hash}`;
}
function initialView(){
 const value=new URLSearchParams(location.search).get('todo');
 return VIEWS.has(value)?value:'today';
}
function unwrapActions(payload){return Array.isArray(payload)?payload:(payload?.actions||[])}
function requestId(){return crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(16).slice(2)}`}

function ActionRow({item,text,busy,onPrimary}){
 const primary=item.primary_action||{};
 const canRun=(item.kind==='task'&&['complete','reopen'].includes(primary.id))||(item.kind==='routine'&&primary.id==='record_done');
 const actionLabel=item.kind==='routine'?text.record:(primary.id==='reopen'?text.reopen:text.complete);
 const metadata=[];
 if(item.context?.list?.name)metadata.push(item.context.list.name);
 if(item.assignee?.username)metadata.push(item.assignee.username);
 if(item.state==='overdue')metadata.push(text.overdue);
 else if(item.state==='active'||item.state==='waiting')metadata.push(item.state==='active'?'In progress':'Waiting');
 return <article className={`todo-row urgency-${item.urgency||'normal'}`} data-action-id={item.id}>
  <button className="todo-complete" type="button" onClick={()=>onPrimary(item)} disabled={busy||!canRun} aria-label={`${actionLabel}: ${item.title}`} title={actionLabel}><Icon name={item.kind==='routine'?'history':'check'} size={18}/></button>
  <a className="todo-row-main" href={item.deep_link||legacyHref(item.kind==='routine'?'routines':'tasks')}>
   <strong>{item.title}</strong>
   {metadata.length>0&&<span>{metadata.slice(0,2).join(' · ')}</span>}
  </a>
  <a className="todo-overflow" href={item.deep_link||legacyHref(item.kind==='routine'?'routines':'tasks')} aria-label={`${text.open}: ${item.title}`}><Icon name="more" size={18}/></a>
 </article>
}

function Section({title,items,text,busyId,onPrimary}){
 if(!items.length)return null;
 return <section className="todo-section"><h2>{title}</h2><div className="todo-rows">{items.map(item=><ActionRow key={item.id} item={item} text={text} busy={busyId===item.id} onPrimary={onPrimary}/>)}</div></section>
}

export default function TodoHub({family,data,onCreate}){
 const {i18n}=useTranslation();
 const text=labels[i18n.language?.startsWith('en')?'en':'de'];
 const [view,setViewState]=useState(initialView);
 const [actions,setActions]=useState([]);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [busyId,setBusyId]=useState('');
 const [notice,setNotice]=useState('');
 const [lastAction,setLastAction]=useState(null);
 const undoRef=useRef(null);
 const [kind,setKind]=useState('task');
 const [title,setTitle]=useState('');
 const [when,setWhen]=useState('');
 const [assignee,setAssignee]=useState('');
 const [taskList,setTaskList]=useState(data?.task_lists?.[0]?.id||'');
 const [routinePreset,setRoutinePreset]=useState('daily');
 const [reminder,setReminder]=useState(false);
 const [adding,setAdding]=useState(false);

 const refresh=useCallback(async(targetView=view)=>{
  if(!family?.id)return;
  setLoading(true);setError('');
  try{
   const scope=targetView==='upcoming'?'upcoming':'today';
   setActions(unwrapActions(await api(`/actions/?scope=${scope}`)));
  }catch(err){setError(err.message||text.loadFailed)}finally{setLoading(false)}
 },[family?.id,text.loadFailed,view]);
 useEffect(()=>{if(view==='today'||view==='upcoming')refresh(view);else setLoading(false)},[view,refresh]);
 useEffect(()=>{setTaskList(data?.task_lists?.[0]?.id||'')},[family?.id,data?.task_lists]);
 useEffect(()=>{if(lastAction)requestAnimationFrame(()=>undoRef.current?.focus())},[lastAction]);

 function setView(next){
  if(!VIEWS.has(next))return;
  const url=new URL(location.href);
  if(next==='today')url.searchParams.delete('todo');else url.searchParams.set('todo',next);
  history.replaceState({...history.state,todoView:next},'',`${url.pathname}${url.search}${url.hash}`);
  setViewState(next);setNotice('');setLastAction(null);
 }
 async function onPrimary(item){
  if(busyId)return;
  const primary=item.primary_action||{};
  setBusyId(item.id);setError('');
  try{
   if(item.kind==='task'&&['complete','reopen'].includes(primary.id)){
    const endpoint=apiPath(primary.href);
    await api(endpoint,{method:'POST'});
    setLastAction({itemId:item.id,title:item.title,undo:()=>api(endpoint,{method:'POST'})});
   }else if(item.kind==='routine'&&primary.id==='record_done'){
    const endpoint=apiPath(primary.href);const rid=requestId();
    const log=await api(endpoint,{method:'POST',body:JSON.stringify({request_id:rid})});
    if(!log?.id)throw new Error('routine_log_missing');
    setLastAction({itemId:item.id,title:item.title,undo:()=>api(`/routines/${item.id.split(':')[1]}/logs/${log.id}/`,{method:'DELETE'})});
   }else return;
   setNotice(text.saved);await refresh(view);
  }catch(err){setError(err.message||text.saveFailed);setLastAction(null)}finally{setBusyId('')}
 }
 async function undo(){
  if(!lastAction)return;
  const previous=lastAction;setBusyId(previous.itemId);
  try{await previous.undo();setLastAction(null);setNotice(text.undone);await refresh(view);setTimeout(()=>document.querySelector(`[data-action-id="${CSS.escape(previous.itemId)}"] .todo-complete`)?.focus(),0)}catch(err){setError(err.message||text.saveFailed)}finally{setBusyId('')}
 }
 async function quickAdd(event){
  event.preventDefault();const clean=title.trim();if(!clean||adding)return;
  setAdding(true);setError('');
  try{
   if(kind==='task'){
    const payload={family:family.id,title:clean};
    if(taskList)payload.task_list=taskList;
    if(assignee)payload.assignee=assignee;
    if(when)payload.due_at=dueAt(when);
    await api('/smart/tasks/quick-add/',{method:'POST',body:JSON.stringify(payload)});
   }else{
    const presets={daily:[1,1],weekly:[1,7],three:[3,7]};const [target_count,target_period_days]=presets[routinePreset]||presets.daily;
    await api('/routines/',{method:'POST',body:JSON.stringify({family:family.id,name:clean,target_count,target_period_days,reminder_enabled:reminder,active:true})});
   }
   setTitle('');setNotice(kind==='task'?`${text.task} ✓`:`${text.routine} ✓`);await refresh(view==='upcoming'?'upcoming':'today');
  }catch(err){setError(err.message||text.saveFailed)}finally{setAdding(false)}
 }

 const groups=useMemo(()=>{
  const remaining=new Set(actions.map(item=>item.id));
  const take=predicate=>actions.filter(item=>remaining.has(item.id)&&predicate(item)).map(item=>{remaining.delete(item.id);return item});
  return {
   overdue:take(item=>item.state==='overdue'),
   today:take(item=>item.kind==='task'&&item.state==='due'),
   routines:take(item=>item.kind==='routine'&&!['done_today','done','paused'].includes(item.state)),
   progress:take(item=>item.kind==='task'&&['active','waiting'].includes(item.state)),
   next:take(()=>true),
  };
 },[actions]);
 const tabItems=[['today',text.today],['upcoming',text.upcoming],['lists',text.lists],['more',text.more]];
 const memberships=family?.memberships||[];const taskLists=data?.task_lists||[];

 return <div className="todo-hub">
  <header className="todo-head"><div><span className="eyebrow">FamilyOS</span><h1 tabIndex="-1">{text.title}</h1></div></header>
  <nav className="todo-tabs" aria-label={text.title}>{tabItems.map(([id,label])=><button key={id} type="button" className={view===id?'active':''} aria-current={view===id?'page':undefined} onClick={()=>setView(id)}>{label}</button>)}</nav>
  {(view==='today'||view==='upcoming')&&<>
   <form className="todo-quick" onSubmit={quickAdd}>
    <div className="todo-quick-head"><strong>{text.quick}</strong><div className="todo-kind" role="group" aria-label={text.quick}><button type="button" className={kind==='task'?'active':''} aria-pressed={kind==='task'} onClick={()=>setKind('task')}>{text.task}</button><button type="button" className={kind==='routine'?'active':''} aria-pressed={kind==='routine'} onClick={()=>setKind('routine')}>{text.routine}</button></div></div>
    <div className="todo-quick-main"><label className="sr-only" htmlFor="todo-quick-title">{kind==='task'?text.task:text.routine}</label><input id="todo-quick-title" value={title} onChange={event=>setTitle(event.target.value)} placeholder={kind==='task'?text.titlePlaceholder:text.routinePlaceholder}/><button className="primary" type="submit" disabled={!title.trim()||adding}>{adding?text.adding:text.add}</button></div>
    {kind==='task'?<div className="todo-chips"><button type="button" className={when==='today'?'selected':''} aria-pressed={when==='today'} onClick={()=>setWhen(when==='today'?'':'today')}>{text.todayChip}</button><button type="button" className={when==='tomorrow'?'selected':''} aria-pressed={when==='tomorrow'} onClick={()=>setWhen(when==='tomorrow'?'':'tomorrow')}>{text.tomorrow}</button><label><span>{text.person}</span><select value={assignee} onChange={event=>setAssignee(event.target.value)}><option value="">{text.none}</option>{memberships.map(member=><option key={member.id} value={member.user}>{member.display_name||member.username}</option>)}</select></label><label><span>{text.list}</span><select value={taskList} onChange={event=>setTaskList(event.target.value)}><option value="">{text.none}</option>{taskLists.map(list=><option key={list.id} value={list.id}>{list.name}</option>)}</select></label><button type="button" onClick={()=>onCreate?.('task',{taskListId:taskList})}>{text.fullEditor}</button></div>:<div className="todo-chips"><label><span>{text.routinePreset}</span><select value={routinePreset} onChange={event=>setRoutinePreset(event.target.value)}><option value="daily">{text.daily}</option><option value="weekly">{text.weekly}</option><option value="three">{text.threeWeekly}</option></select></label><label className="todo-checkbox"><input type="checkbox" checked={reminder} onChange={event=>setReminder(event.target.checked)}/><span>{text.reminder}</span></label><button type="button" onClick={()=>onCreate?.('routine')}>{text.fullEditor}</button></div>}
   </form>
   <div className="todo-live" role="status" aria-live="polite">{notice}{lastAction&&<button ref={undoRef} type="button" onClick={undo} disabled={busyId===lastAction.itemId}><Icon name="refresh" size={14}/> {text.undo}</button>}</div>
   {error&&<div className="todo-error" role="alert">{error}<button type="button" onClick={()=>refresh(view)}><Icon name="refresh" size={14}/></button></div>}
   {loading?<div className="todo-loading" role="status"><Icon name="refresh"/>…</div>:actions.length===0?<div className="todo-empty"><Icon name="check" size={24}/><span>{text.empty}</span></div>:view==='upcoming'?<Section title={text.upcoming} items={actions} text={text} busyId={busyId} onPrimary={onPrimary}/>:<><Section title={text.overdue} items={groups.overdue} text={text} busyId={busyId} onPrimary={onPrimary}/><Section title={text.dueToday} items={groups.today} text={text} busyId={busyId} onPrimary={onPrimary}/><Section title={text.routinesNow} items={groups.routines} text={text} busyId={busyId} onPrimary={onPrimary}/><Section title={text.inProgress} items={groups.progress} text={text} busyId={busyId} onPrimary={onPrimary}/><Section title={text.next} items={groups.next} text={text} busyId={busyId} onPrimary={onPrimary}/></>}
  </>}
  {view==='lists'&&<div className="todo-link-grid"><a href={legacyHref('tasks')}><Icon name="tasks"/><span><strong>{text.allTasks}</strong><small>{text.allTasksHint}</small></span><Icon name="next"/></a>{taskLists.map(list=><a key={list.id} href={legacyHref('tasks',{list:list.id})}><Icon name="lists"/><span><strong>{list.name}</strong><small>{list.open_count??0} offen</small></span><Icon name="next"/></a>)}<a href={legacyHref('routines')}><Icon name="history"/><span><strong>{text.allRoutines}</strong><small>{text.allRoutinesHint}</small></span><Icon name="next"/></a></div>}
  {view==='more'&&<div className="todo-link-grid"><a href={legacyHref('tasks',{mode:'completed'})}><Icon name="doneAll"/><span><strong>{text.completed}</strong><small>{text.completedHint}</small></span><Icon name="next"/></a><a href={legacyHref('tasks',{mode:'workflow'})}><Icon name="progress"/><span><strong>{text.workflows}</strong><small>{text.workflowsHint}</small></span><Icon name="next"/></a><a href={legacyHref('routines')}><Icon name="history"/><span><strong>{text.allRoutines}</strong><small>{text.allRoutinesHint}</small></span><Icon name="next"/></a></div>}
 </div>
}