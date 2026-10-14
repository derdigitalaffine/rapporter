import {Icon} from './icons';
import {useState} from 'react';
import MemberAvatar from './MemberAvatar';
import ActionOptionsEditor from './ActionOptionsEditor';
import './unified-actions.css';
import {assignmentCopy} from './game-assignment-i18n';
import './todo-hub.css';
import './todo-action-row.css';

const strings={
  de:{complete:'Erledigen',reopen:'Wieder öffnen',record:'Erledigt',reactivate:'Aktivieren',open:'Öffnen',actions:'Schnellaktionen',actionOptions:'Optionen für',snooze:'24 Std. pausieren',edit:'Bearbeiten',duel:'Zuweisung ausspielen',move:'Verschieben',delete:'Löschen',overdue:'Überfällig',active:'In Arbeit',waiting:'Wartet'},
  en:{complete:'Complete',reopen:'Reopen',record:'Done',reactivate:'Reactivate',open:'Open',actions:'Quick actions',actionOptions:'Options for',snooze:'Snooze 24h',edit:'Edit',duel:'Play for assignment',move:'Move',delete:'Delete',overdue:'Overdue',active:'In progress',waiting:'Waiting'},
};

function textFor(language){return strings[String(language||'').startsWith('en')?'en':'de']}
function fallbackHref(item){return `/?page=${item.kind==='routine'?'routines':'tasks'}`}
function primaryLabel(item,text){
  const id=item?.primary_action?.id;
  if(item.kind==='routine')return id==='reactivate'?text.reactivate:text.record;
  return id==='reopen'?text.reopen:text.complete;
}
function canRunPrimary(item){
  const id=item?.primary_action?.id;
  return (item.kind==='task'&&['complete','reopen'].includes(id))||(item.kind==='routine'&&['record_done','reactivate'].includes(id));
}
function secondaryActions(item){
  const primaryId=item?.primary_action?.id;
  return (item?.allowed_actions||[]).filter(action=>action?.id!==primaryId&&['snooze','edit','duel','move','delete'].includes(action?.id));
}
function linkFor(item,action){
  if(action.id==='duel')return action.href;
  const raw=item.deep_link||fallbackHref(item);
  if(action.id!=='move')return raw;
  const url=new URL(raw,location.origin);url.searchParams.set('mode','workflow');return `${url.pathname}${url.search}${url.hash}`;
}
function secondaryLabel(action,text){return action.id==='snooze'?text.snooze:action.id==='duel'?text.duel:action.id==='move'?text.move:action.id==='delete'?text.delete:text.edit}

export default function TodoActionRow({item,language,busy=false,onPrimary,onSecondary}){
  const [editing,setEditing]=useState(false);
  const text={...textFor(language),duel:assignmentCopy(language).duel};const actionLabel=primaryLabel(item,text);const secondary=secondaryActions(item);const metadata=[];
  const expected=item.prediction_v2?.expected_at||item.due_at||item.next_due_at;
  if(expected){const date=new Date(expected);if(!Number.isNaN(date.getTime()))metadata.push(date.toLocaleString(language||'de',{dateStyle:'short',...(item.prediction_v2?.day_only?{}:{timeStyle:'short'})}));}
  if(item.context?.list?.name)metadata.push(item.context.list.name);
  if(item.context?.workflow?.name)metadata.push(item.context.workflow.name);
  if(item.assignee?.username)metadata.push(item.assignee.username);
  if(item.state==='overdue')metadata.push(text.overdue);
  else if(item.state==='active'||item.state==='waiting')metadata.push(item.state==='active'?text.active:text.waiting);
  return <article className={`todo-row urgency-${item.urgency||'normal'}`} data-action-id={item.id} data-accent={item.accent_token||''}>
    <button className="todo-complete" type="button" onClick={()=>onPrimary?.(item)} disabled={busy||!canRunPrimary(item)} aria-label={`${actionLabel}: ${item.title}`} title={actionLabel}><Icon name={item.kind==='routine'?(item.primary_action?.id==='reactivate'?'refresh':'history'):'check'} size={18}/></button>
    <a className="todo-row-main" href={item.deep_link||fallbackHref(item)}>
      <strong className="todo-row-icon"><Icon name={item.icon||'tasks'} size={16}/>{item.title}</strong>{item.assignee&&<MemberAvatar person={item.assignee} size={22}/>}

      {metadata.length>0&&<span>{metadata.slice(0,2).join(' · ')}</span>}
    </a>
    {item.contexts?.length>0&&<div className="action-context-chips">{item.contexts.map(context=><a key={`${context.type}:${context.id}`} href={context.deep_link}><Icon name="link" size={12}/>{context.type}</a>)}</div>}
    {secondary.length?<details className="todo-actions-menu">
      <summary aria-label={`${text.actions}: ${item.title}`} title={text.actions}><Icon name="more" size={18}/></summary>
      <div className="todo-actions-popover" role="group" aria-label={`${text.actionOptions} ${item.title}`}>
        {item.completion_command&&<button type="button" onClick={event=>{event.currentTarget.closest('details')?.removeAttribute('open');setEditing(true)}}><Icon name="settings"/><span>{String(language).startsWith('en')?'Schedule & appearance':'Zeitplan & Darstellung'}</span></button>}{secondary.map(action=>['snooze','delete'].includes(action.id)?<button className={action.id==='delete'?'todo-action-danger':undefined} key={`${action.id}:${action.href}`} type="button" disabled={busy} onClick={event=>{event.currentTarget.closest('details')?.removeAttribute('open');onSecondary?.(item,action)}}><Icon name={action.id==='delete'?'delete':'history'} size={16}/><span>{secondaryLabel(action,text)}</span></button>:<a key={`${action.id}:${action.href}`} href={linkFor(item,action)}><Icon name={action.id==='move'?'progress':action.id==='duel'?'members':'edit'} size={16}/><span>{secondaryLabel(action,text)}</span></a>)}
      </div>
    </details>:<a className="todo-overflow" href={item.deep_link||fallbackHref(item)} aria-label={`${text.open}: ${item.title}`}><Icon name="more" size={18}/></a>}
    {editing&&<ActionOptionsEditor item={item} onClose={()=>setEditing(false)}/>}
  </article>;
}
