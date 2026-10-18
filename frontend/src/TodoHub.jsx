import {SYNC_CHANGED} from './offline-sync-engine';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {confirmAction} from './feedback';
import {Icon} from './icons';
import TodoActionRow from './TodoActionRow';
import ActionCapture from './ActionCapture';
import ActionSettings from './ActionSettings';
import FamilySheet from './ui/FamilySheet';
import {TaskEditor} from './SmartEditors';
import {SmartTasks} from './SmartLists';
import RoutineEditor from './RoutineEditor';
import {DEFAULT_TODO_VIEW_PREFERENCES,TODO_VIEWS as VIEWS,groupActions,isWorkView,normalizeTodoViewPreferences,scopeForView,workspaceView,visibleActions} from './todo-workspace';
import {runTodoPrimary,runTodoSecondary} from './todo-action-runner';
import {pageFromLocation,updateFeatureLocation} from './navigation';
import './todo-hub.css';
import './smart-todo.css';
import './todo-workspace.css';

const DEFAULT_PREFERENCES={smart_ranking_enabled:true,today_sort:'smart',pinned_action_ids:[],hidden_focus_action_ids:[]};
const labels={
 de:{title:'To-dos',today:'Heute',upcoming:'Anstehend',lists:'Listen',more:'Mehr',overdue:'Überfällig',due:'Fällig',routinesNow:'Routinen',inProgress:'In Arbeit / wartet',next:'Als Nächstes',capture:'Ich habe gerade …',empty:'Hier ist gerade nichts offen.',undo:'Rückgängig',undone:'Änderung rückgängig gemacht.',saved:'Änderung gespeichert. Rückgängig ist möglich.',snoozed:'Routine für 24 Stunden pausiert.',deleted:'Aufgabe gelöscht.',deleteTask:'Aufgabe löschen',delete:'Löschen',deleteTaskMessage:'Diese Aufgabe wird dauerhaft gelöscht:',deleteFailed:'Aufgabe konnte nicht gelöscht werden.',loadFailed:'To-dos konnten nicht geladen werden.',saveFailed:'Änderung konnte nicht gespeichert werden.',allTasks:'Aufgaben & Listen',allTasksHint:'Listen, Workflows und vollständige Aufgabendetails',allRoutines:'Routinen verwalten',allRoutinesHint:'Rhythmen, Erinnerungen und Verlauf',completed:'Erledigt & Verlauf',completedHint:'Abgeschlossene Aufgaben wiederfinden',workflows:'Workflows / Kanban',workflowsHint:'Statusspalten und Boards weiterverwenden',focusTitle:'Als Nächstes',focusHint:'Warum diese Vorschläge?',pin:'Anpinnen',unpin:'Pin lösen',hideFocus:'Aus Fokus ausblenden',smartSettings:'Smart To-do',smartEnabled:'Smart Ranking',smartHint:'Priorisiert nur sichtbar und erklärbar. Es werden keine Aufgaben oder Routinen automatisch verändert.',sortLabel:'Heute sortieren',sortSmart:'Smart & fachlich',sortChronological:'Chronologisch',resetSmart:'Präferenzen zurücksetzen',prefsSaved:'To-do-Präferenz gespeichert.',reasonPinned:'Von dir angepinnt',reasonOverdue:'Überfällig',reasonDueToday:'Heute fällig',reasonRoutineDue:'Routine ist wieder dran',reasonAssigned:'Dir zugewiesen',reasonHigh:'Hohe Priorität',reasonActive:'In Arbeit',reasonWaiting:'Wartet',reasonNormal:'Fachlich als Nächstes'},
 en:{title:'To-dos',today:'Today',upcoming:'Upcoming',lists:'Lists',more:'More',overdue:'Overdue',due:'Due',routinesNow:'Routines',inProgress:'In progress / waiting',next:'Up next',capture:'I just …',empty:'Nothing needs attention here.',undo:'Undo',undone:'Change undone.',saved:'Change saved. Undo is available.',snoozed:'Routine snoozed for 24 hours.',deleted:'Task deleted.',deleteTask:'Delete task',delete:'Delete',deleteTaskMessage:'This task will be permanently deleted:',deleteFailed:'Could not delete the task.',loadFailed:'Could not load to-dos.',saveFailed:'Could not save the change.',allTasks:'Tasks & lists',allTasksHint:'Lists, workflows and full task details',allRoutines:'Manage routines',allRoutinesHint:'Cadence, reminders and history',completed:'Completed & history',completedHint:'Find completed tasks again',workflows:'Workflows / Kanban',workflowsHint:'Keep using status columns and boards',focusTitle:'Up next',focusHint:'Why these suggestions?',pin:'Pin',unpin:'Unpin',hideFocus:'Hide from focus',smartSettings:'Smart To-do',smartEnabled:'Smart ranking',smartHint:'Only prioritizes visible, explainable items. It never changes tasks or routines automatically.',sortLabel:'Sort Today',sortSmart:'Smart & domain-based',sortChronological:'Chronological',resetSmart:'Reset preferences',prefsSaved:'To-do preference saved.',reasonPinned:'Pinned by you',reasonOverdue:'Overdue',reasonDueToday:'Due today',reasonRoutineDue:'Routine is due again',reasonAssigned:'Assigned to you',reasonHigh:'High priority',reasonActive:'In progress',reasonWaiting:'Waiting',reasonNormal:'Next by domain rules'}
};

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
function readViewPreferences(key){
 if(typeof localStorage==='undefined')return DEFAULT_TODO_VIEW_PREFERENCES;
 try{return normalizeTodoViewPreferences(JSON.parse(localStorage.getItem(key)||'{}'))}catch{return DEFAULT_TODO_VIEW_PREFERENCES}
}
function groupTitle(group,text){return group.label||text[group.labelKey]||group.key}

function Section({title,items,language,busyId,onPrimary,onSecondary,onOpen,density='compact',defaultOpen=false}){
 const [open,setOpen]=useState(defaultOpen);
 if(!items.length)return null;
 return <details className="todo-section" open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
  <summary><span>{title}</span><span className="todo-section-count" aria-label={`${items.length}`}>{items.length}</span><Icon name="next" size={15}/></summary>
  <div className="todo-rows">{items.map(item=><TodoActionRow key={item.id} item={item} language={language} density={density} busy={busyId===item.id} onPrimary={onPrimary} onSecondary={onSecondary} onOpen={onOpen}/>)}</div>
 </details>
}

function CaptureSection({family,text}){
 const [open,setOpen]=useState(false);
 const [busy,setBusy]=useState(false);
 const [dirty,setDirty]=useState(false);
 async function close(){if(busy)return;if(dirty&&!await confirmAction({title:text.close,message:text.deleteCaptureDraft,confirmLabel:text.discard,cancelLabel:text.keepEditing}))return;setDirty(false);setOpen(false)}
 return <><button className="todo-capture-trigger secondary" type="button" onClick={()=>setOpen(true)}><Icon name="doneAll" size={17}/><span>{text.capture}</span></button>{open&&<FamilySheet labelledBy="todo-capture-title" busy={busy} onClose={close}><div className="sheet-head"><h2 id="todo-capture-title">{text.capture}</h2><button className="sheet-close" type="button" disabled={busy} onClick={close} aria-label={text.close}><Icon name="close"/></button></div><ActionCapture family={family} onBusyChange={setBusy} onDirtyChange={setDirty}/></FamilySheet>}</>;
}

function FocusSection({items,text,language,busyId,onPrimary,onSecondary,onPreference,onOpen,density}){
 if(!items.length)return null;
 return <section className="todo-focus" aria-labelledby="todo-focus-title">
  <div className="todo-focus-head"><div><h2 id="todo-focus-title">{text.focusTitle}</h2><span>{text.focusHint}</span></div></div>
  <div className="todo-focus-list">{items.map(item=><div className="todo-focus-item" key={item.id}>
   <TodoActionRow item={item} language={language} density={density} busy={busyId===item.id} onPrimary={onPrimary} onSecondary={onSecondary} onOpen={onOpen}/>
   <div className="todo-focus-meta"><span>{(item.smart?.reasons||['normal']).map(reason=>reasonText(reason,text)).join(' · ')}</span><div>
    <button type="button" onClick={()=>onPreference(item.id,{pinned:!item.smart?.pinned})} aria-label={`${item.smart?.pinned?text.unpin:text.pin}: ${item.title}`}>{item.smart?.pinned?text.unpin:text.pin}</button>
    <button type="button" onClick={()=>onPreference(item.id,{hidden_from_focus:true})} aria-label={`${text.hideFocus}: ${item.title}`}>{text.hideFocus}</button>
   </div></div>
  </div>)}</div>
 </section>
}

function ViewOptions({text,value,onChange}){
 const groupLabels={date:text.groupDate,status:text.groupStatus,list:text.groupList,person:text.groupPerson,none:text.groupNone};
 const sortLabels={due:text.sortDue,priority:text.sortPriority,title:text.sortTitle};
 const densityLabels={compact:text.densityCompact,comfortable:text.densityComfortable};
 return <details className="todo-view-options">
  <summary><Icon name="settings" size={16}/><span>{text.viewOptions}</span><small>{groupLabels[value.group]} · {sortLabels[value.sort]} · {densityLabels[value.density]}</small></summary>
  <div className="todo-view-option-fields">
   <label>{text.groupBy}<select value={value.group} onChange={event=>onChange('group',event.target.value)}><option value="date">{text.groupDate}</option><option value="status">{text.groupStatus}</option><option value="list">{text.groupList}</option><option value="person">{text.groupPerson}</option><option value="none">{text.groupNone}</option></select></label>
   <label>{text.sortBy}<select value={value.sort} onChange={event=>onChange('sort',event.target.value)}><option value="due">{text.sortDue}</option><option value="priority">{text.sortPriority}</option><option value="title">{text.sortTitle}</option></select></label>
   <label>{text.density}<select value={value.density} onChange={event=>onChange('density',event.target.value)}><option value="compact">{text.densityCompact}</option><option value="comfortable">{text.densityComfortable}</option></select></label>
  </div>
 </details>
}

export function TasksWorkspace(props){return <TodoHub {...props} initialWorkspace="lists"/>}
export function RecurringWorkspace(props){return <TodoHub {...props} initialWorkspace="all" recurringOnly/>}

export default function TodoHub({family,data,onCreate,onChanged,currentUserId,userId,initialWorkspace='upcoming',recurringOnly=false}){
 const {i18n}=useTranslation();
 const language=i18n.language||'de';const de=!language.startsWith('en');const text={...labels[de?'de':'en'],title:de?'Aufgaben':'Tasks',all:de?'Alle':'All',routinesNow:de?'Wiederkehrend':'Recurring',close:de?'Schließen':'Close',discard:de?'Verwerfen':'Discard',keepEditing:de?'Weiter bearbeiten':'Keep editing',deleteCaptureDraft:de?'Die noch nicht gespeicherte Eingabe verwerfen?':'Discard the unsaved entry?',viewOptions:de?'Ansicht':'View',groupBy:de?'Gruppieren':'Group by',groupDate:de?'Datum':'Date',groupStatus:de?'Status':'Status',groupList:de?'Liste':'List',groupPerson:de?'Person':'Person',groupNone:de?'Keine':'None',sortBy:de?'Sortieren':'Sort',sortDue:de?'Fälligkeit':'Due date',sortPriority:de?'Priorität':'Priority',sortTitle:de?'Titel A–Z':'Title A–Z',density:de?'Dichte':'Density',densityCompact:de?'Kompakt':'Compact',densityComfortable:de?'Komfortabel':'Comfortable',tomorrow:de?'Morgen':'Tomorrow',thisWeek:de?'Diese Woche':'This week',later:de?'Später':'Later',undated:de?'Ohne Termin':'No date',noList:de?'Ohne Liste':'No list',noPerson:de?'Nicht zugewiesen':'Unassigned',statusOpen:de?'Offen':'Open',statusActive:de?'In Arbeit':'In progress',statusWaiting:de?'Wartend':'Waiting',statusPaused:de?'Pausiert':'Paused'};
 const [view,setViewState]=useState(()=>workspaceView(location.search,initialWorkspace));
 const [query,setQuery]=useState(''),[list,setList]=useState(''),[person,setPerson]=useState('');
 const [completed,setCompleted]=useState(()=>new URLSearchParams(location.search).get('mode')==='completed');
 const [recurring,setRecurring]=useState(recurringOnly);
 const [editor,setEditor]=useState(null);
 const requestRevision=useRef(0),editorRevision=useRef(0);
 const familyRef=useRef(family?.id);familyRef.current=family?.id;
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
 const viewPreferenceKey=`familyos.todo-view.v1:${family?.id||'none'}:${currentUserId||userId||'anonymous'}`;
 const [viewPreferences,setViewPreferences]=useState(()=>readViewPreferences(viewPreferenceKey));

 const refresh=useCallback(async(targetView=view,{resetFocus=false,background=false}={})=>{
  if(!family?.id||!isWorkView(targetView))return;
  const revision=++requestRevision.current;
  if(!background)setLoading(true);setError('');
  try{
   const scope=scopeForView(targetView,completed);
   const payload=await api(`/actions/?family=${encodeURIComponent(family.id)}&scope=${scope}`);
   const rows=[...unwrapActions(payload)];let next=payload?.next;const seen=new Set();
   while(next){const url=new URL(next,location.origin);if(url.origin!==location.origin||url.pathname!=='/api/actions/'||url.searchParams.get('family')!==String(family.id)||url.searchParams.get('scope')!==scope||seen.has(url.href))throw new Error(text.loadFailed);seen.add(url.href);const page=await api(`${url.pathname.slice(4)}${url.search}`);rows.push(...unwrapActions(page));next=page.next;if(revision!==requestRevision.current)return;}
   if(revision!==requestRevision.current)return;
   setActions(rows.filter(item=>String(item.family||family.id)===String(family.id)));
   if(payload?.preferences)setPreferences(payload.preferences);
   const incoming=Array.isArray(payload?.focus)?payload.focus:[];
   const familyChanged=focusFamilyRef.current!==String(family.id);
   focusFamilyRef.current=String(family.id);
   if(targetView!=='today')setFocus([]);
   else setFocus(current=>(resetFocus||familyChanged)?incoming:stableFocus(current,incoming));
  }catch(err){if(revision===requestRevision.current)setError(err.message||text.loadFailed)}finally{if(revision===requestRevision.current)setLoading(false)}
 },[family?.id,text.loadFailed,view,completed]);
 useEffect(()=>{if(isWorkView(view))refresh(view);else setLoading(false);return()=>{requestRevision.current++}},[view,refresh]);
 useEffect(()=>{const changed=event=>{if(event.detail?.familyId===String(family?.id))refresh(view,{background:true})};window.addEventListener(SYNC_CHANGED,changed);return()=>window.removeEventListener(SYNC_CHANGED,changed)},[family?.id,refresh,view]);
 useEffect(()=>{const handler=event=>{if(String(event.detail?.family)===String(family?.id))refresh(view,{background:true})};window.addEventListener('familyos:actions-changed',handler);return()=>window.removeEventListener('familyos:actions-changed',handler)},[family?.id,refresh,view]);
 useEffect(()=>{setFocus([]);setActions([]);setEditor(null);setLastAction(null);setQuery('');setList('');setPerson('');focusFamilyRef.current='';return()=>{requestRevision.current++;editorRevision.current++}},[family?.id]);
 useEffect(()=>{setViewPreferences(readViewPreferences(viewPreferenceKey))},[viewPreferenceKey]);
 useEffect(()=>{const pop=()=>{setViewState(workspaceView(location.search,initialWorkspace));setEditor(null)};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[initialWorkspace]);
 useEffect(()=>{const params=new URLSearchParams(location.search);const id=params.get('task')||params.get('routine');if(id)openItem({id:`${params.has('task')?'task':'routine'}:${id}`})},[family?.id]);
 useEffect(()=>{if(lastAction&&!loading&&!busyId){const frame=requestAnimationFrame(()=>undoRef.current?.focus());return()=>cancelAnimationFrame(frame)}},[lastAction,loading,busyId]);

 function setView(next){
  if(!VIEWS.has(next))return;
  if(!updateFeatureLocation('todo',{todo:next==='upcoming'?null:next,task:null,routine:null,list:null,mode:null,view:null}))return;
  requestRevision.current++;
  setViewState(next);setNotice('');setLastAction(null);
 }
 function updateViewPreference(key,value){
  setViewPreferences(current=>{
   const next=normalizeTodoViewPreferences({...current,[key]:value});
   try{localStorage.setItem(viewPreferenceKey,JSON.stringify(next))}catch{}
   return next;
  });
 }
 async function openItem(item){
  const [kind,id]=item.id.split(':');if(!['task','routine'].includes(kind)||!id)return;
  const revision=++editorRevision.current;setError('');
  try{const record=await api(`/${kind==='task'?'tasks':'routines'}/${id}/`);if(revision!==editorRevision.current)return;if(!record||String(record.family)!==String(familyRef.current))throw new Error(text.loadFailed);setEditor({kind,record})}catch(err){if(revision===editorRevision.current)setError(err.message||text.loadFailed)}
 }
 function closeEditor(){editorRevision.current++;setEditor(null);const page=pageFromLocation();const params={};if(['todo','tasks'].includes(page))params.task=null;if(['todo','routines'].includes(page))params.routine=null;updateFeatureLocation(page,params,{replace:true,notify:false})}
 async function savedEditor(){closeEditor();await refresh(view,{background:true});onChanged?.()}
 async function onPrimary(item){
  if(busyId)return;setBusyId(item.id);setError('');
  try{
   const result=await runTodoPrimary(item);
   setLastAction({itemId:item.id,title:item.title,undo:result.undo,completion:result.completion});
   setNotice(text.saved);await refresh(view,{background:true});
  }catch(err){setError(err.message||text.saveFailed);setLastAction(null)}finally{setBusyId('')}
 }
 async function onSecondary(item,action){
  if(busyId||!['snooze','delete'].includes(action?.id))return;
  if(action.id==='delete'){
   const ok=await confirmAction({title:text.deleteTask,message:`${text.deleteTaskMessage} “${item.title}”`,confirmLabel:text.delete,danger:true});
   if(!ok){setTimeout(()=>document.querySelector(`[data-action-id="${CSS.escape(item.id)}"] .todo-actions-menu summary`)?.focus(),0);return}
  }
  setBusyId(item.id);setError('');
  try{
   await runTodoSecondary(item,action);setLastAction(null);setNotice(action.id==='delete'?text.deleted:text.snoozed);await refresh(view,{background:true});
   if(action.id==='snooze')setTimeout(()=>document.querySelector(`[data-action-id="${CSS.escape(item.id)}"] .todo-actions-menu summary`)?.focus(),0);
  }catch(err){setError(err.message||(action.id==='delete'?text.deleteFailed:text.saveFailed))}finally{setBusyId('')}
 }
 async function undo(){
  if(!lastAction)return;
  const previous=lastAction;setBusyId(previous.itemId);
  try{await previous.undo();setLastAction(null);setNotice(text.undone);await refresh(view,{background:true});setTimeout(()=>document.querySelector(`[data-action-id="${CSS.escape(previous.itemId)}"] .todo-complete`)?.focus(),0)}catch(err){setError(err.message||text.saveFailed)}finally{setBusyId('')}
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

 const visible=useMemo(()=>visibleActions(actions,{view,query,list,person,completed,recurring}),[actions,view,query,list,person,completed,recurring]);
 const smartFocusActive=view==='today'&&preferences.smart_ranking_enabled!==false&&preferences.today_sort!=='chronological';
 const focusIds=useMemo(()=>new Set(focus.map(item=>item.id)),[focus]);
 const visibleFocus=smartFocusActive?focus.filter(item=>visible.some(row=>row.id===item.id)):[];
 const listActions=useMemo(()=>smartFocusActive?visible.filter(item=>!focusIds.has(item.id)):visible,[visible,focusIds,smartFocusActive]);
 const groups=useMemo(()=>groupActions(listActions,{mode:viewPreferences.group,sort:viewPreferences.sort}),[listActions,viewPreferences.group,viewPreferences.sort]);
 const tabItems=[['upcoming',text.upcoming],['today',text.today],['all',text.all],['more',text.more]];
 const taskLists=data?.task_lists||[];
 const rowProps={language,busyId,onPrimary,onSecondary,onOpen:openItem,density:viewPreferences.density};

 return <div className="todo-hub">
  <h1 className="form-sr-only">{text.title}</h1>
  <nav className="todo-tabs" aria-label={text.title}>{tabItems.map(([id,label])=><button key={id} type="button" className={view===id?'active':''} aria-current={view===id?'page':undefined} onClick={()=>setView(id)}>{label}</button>)}</nav>
  <div className="todo-workspace-actions"><button type="button" className="primary" onClick={()=>onCreate?onCreate('task',{taskListId:list}):setEditor({kind:'task',record:null})}><Icon name="plus"/>{de?'Aufgabe hinzufügen':'Add task'}</button><CaptureSection family={family} text={text}/></div>
  {isWorkView(view)&&<>
   <div className="todo-workspace-filters"><label className="todo-search"><Icon name="search" size={16}/><span className="sr-only">{de?'Aufgaben durchsuchen':'Search tasks'}</span><input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder={de?'Aufgaben suchen':'Search tasks'}/></label><details><summary><Icon name="filter" size={16}/>{de?'Filter':'Filters'}{(list||person||recurring)&&<span aria-label={de?'Aktive Filter':'Active filters'}>•</span>}</summary><div className="todo-filter-fields"><label>{de?'Liste':'List'}<select value={list} onChange={event=>setList(event.target.value)}><option value="">{de?'Alle Listen':'All lists'}</option>{taskLists.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>{de?'Zuständig':'Assigned to'}<select value={person} onChange={event=>setPerson(event.target.value)}><option value="">{de?'Alle':'Everyone'}</option>{(family.memberships||[]).map(member=><option key={member.user} value={member.user}>{member.display_name||member.username}</option>)}</select></label><label><input type="checkbox" checked={recurring} onChange={event=>setRecurring(event.target.checked)}/>{de?'Nur wiederkehrende Aufgaben':'Recurring tasks only'}</label></div></details>{view==='all'&&<label className="todo-completed-filter"><input type="checkbox" checked={completed} onChange={event=>setCompleted(event.target.checked)}/>{de?'Erledigte anzeigen':'Show completed'}</label>}</div>
   <ViewOptions text={text} value={viewPreferences} onChange={updateViewPreference}/>
   <div className="todo-live" role="status" aria-live="polite">{notice}{lastAction&&<button ref={undoRef} type="button" onClick={undo} disabled={busyId===lastAction.itemId}><Icon name="refresh" size={14}/> {text.undo}</button>}</div>
   {loading?<div className="todo-loading" role="status"><Icon name="refresh"/>…</div>:!error&&visible.length===0?<div className="todo-empty"><Icon name="check" size={24}/><span>{query||list||person||recurring?(de?'Keine passenden Aufgaben.':'No matching tasks.'):text.empty}</span></div>:<>
    {smartFocusActive&&<FocusSection items={visibleFocus} text={text} {...rowProps} onPreference={updatePreference}/>} 
    {viewPreferences.group==='none'?<div className="todo-rows todo-rows--ungrouped">{groups[0]?.items.map(item=><TodoActionRow key={item.id} item={item} language={language} density={viewPreferences.density} busy={busyId===item.id} onPrimary={onPrimary} onSecondary={onSecondary} onOpen={openItem}/>)}</div>:groups.map(group=><Section key={`${view}-${viewPreferences.group}-${group.key}`} title={groupTitle(group,text)} items={group.items} {...rowProps} defaultOpen/>)}
   </>}
   {lastAction?.completion?.id&&<div className="action-duration-chips" role="group" aria-label={language.startsWith('en')?'Actual duration':'Tatsächliche Dauer'}>{[5,10,15,30,60].map(minutes=><button key={minutes} type="button" onClick={async()=>{try{await api(`/actions/completions/${lastAction.completion.id}/duration/`,{method:'PATCH',body:JSON.stringify({duration_minutes:minutes})});setNotice(`${minutes} min ✓`)}catch(err){setError(err.message)}}}>{minutes} min</button>)}</div>}
  </>}
  {error&&<div className="todo-error" role="alert">{error}<button type="button" title={de?'Erneut versuchen':'Retry'} aria-label={de?'Erneut versuchen':'Retry'} onClick={()=>refresh(view)}><Icon name="refresh" size={14}/></button></div>}
  {view==='lists'&&<><h2 className="todo-workspace-heading">{text.lists}</h2><SmartTasks family={family} currentUserId={currentUserId||userId} integrated onChanged={onChanged}/></>}
  {view==='more'&&<><div className="todo-workspace-links"><button type="button" onClick={()=>setView('lists')}><Icon name="lists"/>{de?'Listen & Workflows':'Lists & workflows'}<Icon name="next"/></button><button type="button" onClick={()=>{setCompleted(true);setView('all')}}><Icon name="doneAll"/>{text.completed}<Icon name="next"/></button></div><ActionSettings family={family}/><section className="todo-smart-settings" aria-labelledby="todo-smart-settings-title"><h2 id="todo-smart-settings-title">{text.smartSettings}</h2><label className="todo-smart-toggle"><input type="checkbox" checked={preferences.smart_ranking_enabled!==false} onChange={event=>updateSettings({smart_ranking_enabled:event.target.checked})}/><span>{text.smartEnabled}</span></label><label className="todo-smart-sort"><span>{text.sortLabel}</span><select value={preferences.today_sort||'smart'} onChange={event=>updateSettings({today_sort:event.target.value})}><option value="smart">{text.sortSmart}</option><option value="chronological">{text.sortChronological}</option></select></label><button type="button" onClick={()=>updateSettings({reset:true})}>{text.resetSmart}</button></section></>}
  {editor?.kind==='task'&&<TaskEditor family={family} task={editor.record} lists={taskLists} members={family.memberships||[]} defaultListId={list} onClose={closeEditor} onSaved={savedEditor}/>}
  {editor?.kind==='routine'&&<RoutineEditor family={family} routine={editor.record} userId={userId||currentUserId} onClose={closeEditor} onSaved={savedEditor}/>}
 </div>
}