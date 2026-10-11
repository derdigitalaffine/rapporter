import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import TodoActionRow from './TodoActionRow';
import {runTodoPrimary,runTodoSecondary} from './todo-action-runner';
import './todo-hub.css';
import './smart-todo.css';

const VIEWS=new Set(['today','upcoming','lists','more']);
const DEFAULT_PREFERENCES={smart_ranking_enabled:true,today_sort:'smart',pinned_action_ids:[],hidden_focus_action_ids:[]};
const labels={
 de:{title:'To-dos',today:'Heute',upcoming:'Demnächst',lists:'Listen',more:'Mehr',quick:'Schnell hinzufügen',task:'Aufgabe',routine:'Routine',titlePlaceholder:'Was steht an?',routinePlaceholder:'Neue Routine',add:'Hinzufügen',adding:'Wird hinzugefügt…',todayChip:'Heute',tomorrow:'Morgen',person:'Person',list:'Liste',none:'Ohne',routinePreset:'Rhythmus',daily:'Täglich',weekly:'Wöchentlich',threeWeekly:'3× pro Woche',reminder:'Erinnerung',fullEditor:'Alle Felder',overdue:'Überfällig',dueToday:'Heute',routinesNow:'Routinen jetzt',inProgress:'In Arbeit / wartet',next:'Als Nächstes',doneToday:'Heute erledigt',empty:'Hier ist gerade nichts offen.',undo:'Rückgängig',undone:'Änderung rückgängig gemacht.',saved:'Änderung gespeichert. Rückgängig ist möglich.',snoozed:'Routine für 24 Stunden pausiert.',loadFailed:'To-dos konnten nicht geladen werden.',saveFailed:'Änderung konnte nicht gespeichert werden.',allTasks:'Aufgaben & Listen',allTasksHint:'Listen, Workflows und vollständige Aufgabendetails',allRoutines:'Routinen verwalten',allRoutinesHint:'Rhythmen, Erinnerungen und Verlauf',completed:'Erledigt & Verlauf',completedHint:'Abgeschlossene Aufgaben wiederfinden',workflows:'Workflows / Kanban',workflowsHint:'Statusspalten und Boards weiterverwenden',focusTitle:'Als Nächstes',focusHint:'Warum diese Vorschläge?',pin:'Anpinnen',unpin:'Pin lösen',hideFocus:'Aus Fokus ausblenden',smartSettings:'Smart To-do',smartEnabled:'Smart Ranking',smartHint:'Priorisiert nur sichtbar und erklärbar. Es werden keine Aufgaben oder Routinen automatisch verändert.',sortLabel:'Heute sortieren',sortSmart:'Smart & fachlich',sortChronological:'Chronologisch',resetSmart:'Präferenzen zurücksetzen',prefsSaved:'To-do-Präferenz gespeichert.',reasonPinned:'Von dir angepinnt',reasonOverdue:'Überfällig',reasonDueToday:'Heute fällig',reasonRoutineDue:'Routine ist wieder dran',reasonAssigned:'Dir zugewiesen',reasonHigh:'Hohe Priorität',reasonActive:'In Arbeit',reasonWaiting:'Wartet',reasonNormal:'Fachlich als Nächstes'},
 en:{title:'To-dos',today:'Today',upcoming:'Upcoming',lists:'Lists',more:'More',quick:'Quick add',task:'Task',routine:'Routine',titlePlaceholder:'What needs doing?',routinePlaceholder:'New routine',add:'Add',adding:'Adding…',todayChip:'Today',tomorrow:'Tomorrow',person:'Person',list:'List',none:'None',routinePreset:'Cadence',daily:'Daily',weekly:'Weekly',threeWeekly:'3× per week',reminder:'Reminder',fullEditor:'All fields',overdue:'Overdue',dueToday:'Today',routinesNow:'Routines now',inProgress:'In progress / waiting',next:'Up next',doneToday:'Done today',empty:'Nothing needs attention here.',undo:'Undo',undone:'Change undone.',saved:'Change saved. Undo is available.',snoozed:'Routine snoozed for 24 hours.',loadFailed:'Could not load to-dos.',saveFailed:'Could not save the change.',allTasks:'Tasks & lists',allTasksHint:'Lists, workflows and full task details',allRoutines:'Manage routines',allRoutinesHint:'Cadence, reminders and history',completed:'Completed & history',completedHint:'Find completed tasks again',workflows:'Workflows / Kanban',workflowsHint:'Keep using status columns and boards',focusTitle:'Up next',focusHint:'Why these suggestions?',pin:'Pin',unpin:'Unpin',hideFocus:'Hide from focus',smartSettings:'Smart To-do',smartEnabled:'Smart ranking',smartHint:'Only prioritizes visible, explainable items. It never changes tasks or routines automatically.',sortLabel:'Sort Today',sortSmart:'Smart & domain-based',sortChronological:'Chronological',resetSmart:'Reset preferences',prefsSaved:'To-do preference saved.',reasonPinned:'Pinned by you',reasonOverdue:'Overdue',reasonDueToday:'Due today',reasonRoutineDue:'Routine is due again',reasonAssigned:'Assigned to you',reasonHigh:'High priority',reasonActive:'In progress',reasonWaiting:'Waiting',reasonNormal:'Next by domain rules'}
};

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
function unwrapActions(payload){return Array.isArray(payload)?payload:(payload?.actions||payload?.results||[])}
function stableFocus(previous,incoming){
 const byId=new Map(incoming.map(item=>[item.id,item]));
 const kept=previous.filter(item=>byId.has(item.id)).map(item=>byId.get(item.id));
 const seen=new Set(kept.map(item=>item.id));
 return [...kept,...incoming.filter(item=>!seen.has(item.id))].slice(0,5);
}
function reasonText(reason,text){
 const values={pinned:text.reasonPinned,overdue:text.reasonOverdue,due_today:text.reasonDueToday,routine_due:text.reasonRoutineDue,assigned_to_me:text.reasonAssigned,high_priority:text.reasonHigh,workflow_active:text.reasonActive,workflow_waiting:text.reasonWaiting,normal:text.reasonNormal};
 return values[reason]||reason;
}

function Section({title,items,language,busyId,onPrimary,onSecondary}){
 if(!items.length)return null;
 return <section className="todo-section"><h2>{title}</h2><div className="todo-rows">{items.map(item=><TodoActionRow key={item.id} item={item} language={language} busy={busyId===item.id} onPrimary={onPrimary} onSecondary={onSecondary}/>)}</div></section>
}

function FocusSection({items,text,language,busyId,onPrimary,onSecondary,onPreference}){
 if(!items.length)return null;
 return <section className="todo-focus" aria-labelledby="todo-focus-title">
  <div className="todo-focus-head"><div><h2 id="todo-focus-title">{text.focusTitle}</h2><span>{text.focusHint}</span></div></div>
  <div className="todo-focus-list">{items.map(item=><div className="todo-focus-item" key={item.id}>
   <TodoActionRow item={item} language={language} busy={busyId===item.id} onPrimary={onPrimary} onSecondary={onSecondary}/>
   <div className="todo-focus-meta"><span>{(item.smart?.reasons||['normal']).map(reason=>reasonText(reason,text)).join(' · ')}</span><div>
    <button type="button" onClick={()=>onPreference(item.id,{pinned:!item.smart?.pinned})} aria-label={`${item.smart?.pinned?text.unpin:text.pin}: ${item.title}`}>{item.smart?.pinned?text.unpin:text.pin}</button>
    <button type="button" onClick={()=>onPreference(item.id,{hidden_from_focus:true})} aria-label={`${text.hideFocus}: ${item.title}`}>{text.hideFocus}</button>
   </div></div>
  </div>)}</div>
 </section>
}

export default function TodoHub({family,data,onCreate}){
 const {i18n}=useTranslation();
 const language=i18n.language||'de';const text=labels[language.startsWith('en')?'en':'de'];
 const [view,setViewState]=useState(initialView);
 const [actions,setActions]=useState([]);
 const [focus,setFocus]=useState([]);
 const [preferences,setPreferences]=useState(DEFAULT_PREFERENCES);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [busyId,setBusyId]=useState('');
 const [notice,setNotice]=useState('');
 const [lastAction,setLastAction]=useState(null);
 const undoRef=useRef(null);
 const focusFamilyRef=useRef('');
 const [kind,setKind]=useState('task');
 const [title,setTitle]=useState('');
 const [when,setWhen]=useState('');
 const [assignee,setAssignee]=useState('');
 const [taskList,setTaskList]=useState(data?.task_lists?.[0]?.id||'');
 const [routinePreset,setRoutinePreset]=useState('daily');
 const [reminder,setReminder]=useState(false);
 const [adding,setAdding]=useState(false);

 const refresh=useCallback(async(targetView=view,{resetFocus=false}={})=>{
  if(!family?.id)return;
  setLoading(true);setError('');
  try{
   const scope=targetView==='upcoming'?'upcoming':'today';
   const payload=await api(`/actions/?family=${encodeURIComponent(family.id)}&scope=${scope}`);
   setActions(unwrapActions(payload));
   if(payload?.preferences)setPreferences(payload.preferences);
   const incoming=Array.isArray(payload?.focus)?payload.focus:[];
   const familyChanged=focusFamilyRef.current!==String(family.id);
   focusFamilyRef.current=String(family.id);
   if(targetView!=='today')setFocus([]);
   else setFocus(current=>(resetFocus||familyChanged)?incoming:stableFocus(current,incoming));
  }catch(err){setError(err.message||text.loadFailed)}finally{setLoading(false)}
 },[family?.id,text.loadFailed,view]);
 useEffect(()=>{if(view==='today'||view==='upcoming')refresh(view);else setLoading(false)},[view,refresh]);
 useEffect(()=>{setTaskList(data?.task_lists?.[0]?.id||'');setFocus([]);focusFamilyRef.current=''},[family?.id,data?.task_lists]);
 useEffect(()=>{if(lastAction&&!loading)requestAnimationFrame(()=>undoRef.current?.focus())},[lastAction,loading]);

 function setView(next){
  if(!VIEWS.has(next))return;
  const url=new URL(location.href);
  if(next==='today')url.searchParams.delete('todo');else url.searchParams.set('todo',next);
  history.replaceState({...history.state,todoView:next},'',`${url.pathname}${url.search}${url.hash}`);
  setViewState(next);setNotice('');setLastAction(null);
 }
 async function onPrimary(item){
  if(busyId)return;setBusyId(item.id);setError('');
  try{
   const result=await runTodoPrimary(item);
   setLastAction({itemId:item.id,title:item.title,undo:result.undo});
   setNotice(text.saved);await refresh(view);
  }catch(err){setError(err.message||text.saveFailed);setLastAction(null)}finally{setBusyId('')}
 }
 async function onSecondary(item,action){
  if(busyId||action?.id!=='snooze')return;setBusyId(item.id);setError('');
  try{
   await runTodoSecondary(item,action);setLastAction(null);setNotice(text.snoozed);await refresh(view);
   setTimeout(()=>document.querySelector(`[data-action-id="${CSS.escape(item.id)}"] .todo-actions-menu summary`)?.focus(),0);
  }catch(err){setError(err.message||text.saveFailed)}finally{setBusyId('')}
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
 async function updatePreference(actionId,changes){
  if(!family?.id)return;
  setError('');
  try{
   const payload=await api(`/actions/?family=${encodeURIComponent(family.id)}`,{method:'PATCH',body:JSON.stringify({action_id:actionId,...changes})});
   setPreferences(payload||DEFAULT_PREFERENCES);setNotice(text.prefsSaved);
   if(view==='today')await refresh('today',{resetFocus:true});
  }catch(err){setError(err.message||text.saveFailed)}
 }
 async function updateSettings(changes){
  if(!family?.id)return;
  const previous=preferences;
  const optimistic=changes.reset?DEFAULT_PREFERENCES:{...preferences,...changes};
  setPreferences(optimistic);
  if(changes.smart_ranking_enabled===false)setFocus([]);
  setError('');
  try{
   const payload=await api(`/actions/?family=${encodeURIComponent(family.id)}`,{method:'PATCH',body:JSON.stringify(changes)});
   setPreferences(payload||DEFAULT_PREFERENCES);setNotice(text.prefsSaved);
   if(view==='today')await refresh('today',{resetFocus:true});
  }catch(err){setPreferences(previous);setError(err.message||text.saveFailed);if(view==='today')await refresh('today',{resetFocus:true})}
 }

 const focusIds=useMemo(()=>new Set(focus.map(item=>item.id)),[focus]);
 const groupedActions=useMemo(()=>view==='today'?actions.filter(item=>!focusIds.has(item.id)):actions,[actions,focusIds,view]);
 const groups=useMemo(()=>{
  const remaining=new Set(groupedActions.map(item=>item.id));
  const take=predicate=>groupedActions.filter(item=>remaining.has(item.id)&&predicate(item)).map(item=>{remaining.delete(item.id);return item});
  return {
   overdue:take(item=>item.state==='overdue'),
   today:take(item=>item.kind==='task'&&item.state==='due'),
   routines:take(item=>item.kind==='routine'&&!['done_today','done','paused'].includes(item.state)),
   progress:take(item=>item.kind==='task'&&['active','waiting'].includes(item.state)),
   next:take(()=>true),
  };
 },[groupedActions]);
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
   {loading?<div className="todo-loading" role="status"><Icon name="refresh"/>…</div>:actions.length===0?<div className="todo-empty"><Icon name="check" size={24}/><span>{text.empty}</span></div>:view==='upcoming'?<Section title={text.upcoming} items={actions} language={language} busyId={busyId} onPrimary={onPrimary} onSecondary={onSecondary}/>:<><FocusSection items={focus} text={text} language={language} busyId={busyId} onPrimary={onPrimary} onSecondary={onSecondary} onPreference={updatePreference}/><Section title={text.overdue} items={groups.overdue} language={language} busyId={busyId} onPrimary={onPrimary} onSecondary={onSecondary}/><Section title={text.dueToday} items={groups.today} language={language} busyId={busyId} onPrimary={onPrimary} onSecondary={onSecondary}/><Section title={text.routinesNow} items={groups.routines} language={language} busyId={busyId} onPrimary={onPrimary} onSecondary={onSecondary}/><Section title={text.inProgress} items={groups.progress} language={language} busyId={busyId} onPrimary={onPrimary} onSecondary={onSecondary}/><Section title={text.next} items={groups.next} language={language} busyId={busyId} onPrimary={onPrimary} onSecondary={onSecondary}/></>}
  </>}
  {view==='lists'&&<div className="todo-link-grid"><a href={legacyHref('tasks')}><Icon name="tasks"/><span><strong>{text.allTasks}</strong><small>{text.allTasksHint}</small></span><Icon name="next"/></a>{taskLists.map(list=><a key={list.id} href={legacyHref('tasks',{list:list.id})}><Icon name="lists"/><span><strong>{list.name}</strong><small>{list.open_count??0} offen</small></span><Icon name="next"/></a>)}<a href={legacyHref('routines')}><Icon name="history"/><span><strong>{text.allRoutines}</strong><small>{text.allRoutinesHint}</small></span><Icon name="next"/></a></div>}
  {view==='more'&&<><section className="todo-smart-settings" aria-labelledby="todo-smart-settings-title"><h2 id="todo-smart-settings-title">{text.smartSettings}</h2><p>{text.smartHint}</p><label className="todo-smart-toggle"><input type="checkbox" checked={preferences.smart_ranking_enabled!==false} onChange={event=>updateSettings({smart_ranking_enabled:event.target.checked})}/><span>{text.smartEnabled}</span></label><label className="todo-smart-sort"><span>{text.sortLabel}</span><select value={preferences.today_sort||'smart'} onChange={event=>updateSettings({today_sort:event.target.value})}><option value="smart">{text.sortSmart}</option><option value="chronological">{text.sortChronological}</option></select></label><button type="button" onClick={()=>updateSettings({reset:true})}>{text.resetSmart}</button></section><div className="todo-link-grid"><a href={legacyHref('tasks',{mode:'completed'})}><Icon name="doneAll"/><span><strong>{text.completed}</strong><small>{text.completedHint}</small></span><Icon name="next"/></a><a href={legacyHref('tasks',{mode:'workflow'})}><Icon name="progress"/><span><strong>{text.workflows}</strong><small>{text.workflowsHint}</small></span><Icon name="next"/></a><a href={legacyHref('routines')}><Icon name="history"/><span><strong>{text.allRoutines}</strong><small>{text.allRoutinesHint}</small></span><Icon name="next"/></a></div></>}
 </div>
}