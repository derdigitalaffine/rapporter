import {useEffect,useRef,useState} from 'react';
import {requestCreate} from './create-request';
import {Icon} from './icons';
import TodoActionRow from './TodoActionRow';
import {runTodoPrimary,runTodoSecondary} from './todo-action-runner';
import {useTodayCoreData} from './todayCoreData';
import './todo-action-row.css';

const strings={
  de:{title:'To-dos',open:'offen',all:'Alle To-dos',addTask:'Aufgabe hinzufügen',empty:'Für heute ist alles erledigt.',loadFailed:'To-dos konnten nicht geladen werden.',saveFailed:'Änderung konnte nicht gespeichert werden.',saved:'Änderung gespeichert. Rückgängig ist möglich.',undo:'Rückgängig',undone:'Änderung rückgängig gemacht.',snoozed:'Routine für 24 Stunden pausiert.',retry:'Erneut laden'},
  en:{title:'To-dos',open:'open',all:'All to-dos',addTask:'Add task',empty:'Everything for today is done.',loadFailed:'Could not load to-dos.',saveFailed:'Could not save the change.',saved:'Change saved. Undo is available.',undo:'Undo',undone:'Change undone.',snoozed:'Routine snoozed for 24 hours.',retry:'Reload'},
};

export default function TodayTodoWidget({family,language,compact=false}){
  const text=strings[String(language||'').startsWith('en')?'en':'de'];
  const core=useTodayCoreData(family);const items=core.actions||[];const loading=core.loading&&!core.loaded;
  const [error,setError]=useState('');const [notice,setNotice]=useState('');const [busyId,setBusyId]=useState('');const [lastAction,setLastAction]=useState(null);const undoRef=useRef(null);
  useEffect(()=>{setNotice('');setLastAction(null);setError('')},[family?.id]);
  useEffect(()=>{if(lastAction&&!loading)requestAnimationFrame(()=>undoRef.current?.focus())},[lastAction,loading]);

  async function refresh(){setError('');await core.refresh()}
  async function onPrimary(item){
    if(busyId)return;setBusyId(item.id);setError('');
    try{const result=await runTodoPrimary(item);setLastAction({itemId:item.id,undo:result.undo});setNotice(text.saved);await core.refresh()}
    catch(err){setError(err.message||text.saveFailed);setLastAction(null)}finally{setBusyId('')}
  }
  async function onSecondary(item,action){
    if(busyId||action?.id!=='snooze')return;setBusyId(item.id);setError('');
    try{await runTodoSecondary(item,action);setLastAction(null);setNotice(text.snoozed);await core.refresh();setTimeout(()=>document.querySelector(`[data-action-id="${CSS.escape(item.id)}"] .todo-actions-menu summary`)?.focus(),0)}
    catch(err){setError(err.message||text.saveFailed)}finally{setBusyId('')}
  }
  async function undo(){
    if(!lastAction)return;const previous=lastAction;setBusyId(previous.itemId);setError('');
    try{await previous.undo();setLastAction(null);setNotice(text.undone);await core.refresh();setTimeout(()=>document.querySelector(`[data-action-id="${CSS.escape(previous.itemId)}"] .todo-complete`)?.focus(),0)}
    catch(err){setError(err.message||text.saveFailed)}finally{setBusyId('')}
  }

  const shown=items.slice(0,compact?3:6);const openCount=items.filter(item=>!['done','done_today'].includes(item.state)).length;const loadError=core.actionFailed?text.loadFailed:'';
  return <section className="today-section today-module today-todo-widget" data-testid="today-todos">
    <div className="today-section-head"><div><h2>{text.title}</h2><small>{openCount} {text.open}</small></div><div className="today-todo-head-actions"><button className="today-add-link" type="button" onClick={()=>requestCreate('task',{source:'todayTodo'})}><Icon name="plus"/> {text.addTask}</button><a className="today-link" href="/?page=todo">{text.all} <Icon name="next"/></a></div></div>
    <div className="today-panel">
      <div className="todo-live" role="status" aria-live="polite">{notice}{lastAction&&<button ref={undoRef} type="button" onClick={undo} disabled={busyId===lastAction.itemId}><Icon name="refresh" size={14}/> {text.undo}</button>}</div>
      {(error||loadError)&&<div className="todo-error" role="alert">{error||loadError}<button type="button" onClick={refresh} aria-label={text.retry}><Icon name="refresh" size={14}/></button></div>}
      {loading?<div className="todo-loading" role="status"><Icon name="refresh"/>…</div>:shown.length?<div className="todo-rows">{shown.map(item=><TodoActionRow key={item.id} item={item} language={language} busy={busyId===item.id} onPrimary={onPrimary} onSecondary={onSecondary}/>)}</div>:<div className="todo-empty"><Icon name="doneAll" size={22}/><span>{text.empty}</span></div>}
    </div>
  </section>;
}
