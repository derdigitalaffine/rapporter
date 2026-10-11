import {Icon} from './icons';
import './todo-hub.css';
import './todo-action-row.css';

const strings={
  de:{complete:'Erledigen',reopen:'Wieder öffnen',record:'Erledigt',reactivate:'Aktivieren',open:'Öffnen',actions:'Schnellaktionen',actionOptions:'Optionen für',snooze:'24 Std. pausieren',edit:'Bearbeiten',move:'Verschieben',overdue:'Überfällig',active:'In Arbeit',waiting:'Wartet'},
  en:{complete:'Complete',reopen:'Reopen',record:'Done',reactivate:'Reactivate',open:'Open',actions:'Quick actions',actionOptions:'Options for',snooze:'Snooze 24h',edit:'Edit',move:'Move',overdue:'Overdue',active:'In progress',waiting:'Waiting'},
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
  return (item?.allowed_actions||[]).filter(action=>action?.id!==primaryId&&['snooze','edit','move'].includes(action?.id));
}
function linkFor(item,action){
  const raw=item.deep_link||fallbackHref(item);
  if(action.id!=='move')return raw;
  const url=new URL(raw,location.origin);url.searchParams.set('mode','workflow');return `${url.pathname}${url.search}${url.hash}`;
}
function secondaryLabel(action,text){return action.id==='snooze'?text.snooze:action.id==='move'?text.move:text.edit}

export default function TodoActionRow({item,language,busy=false,onPrimary,onSecondary}){
  const text=textFor(language);const actionLabel=primaryLabel(item,text);const secondary=secondaryActions(item);const metadata=[];
  if(item.context?.list?.name)metadata.push(item.context.list.name);
  if(item.context?.workflow?.name)metadata.push(item.context.workflow.name);
  if(item.assignee?.username)metadata.push(item.assignee.username);
  if(item.state==='overdue')metadata.push(text.overdue);
  else if(item.state==='active'||item.state==='waiting')metadata.push(item.state==='active'?text.active:text.waiting);
  return <article className={`todo-row urgency-${item.urgency||'normal'}`} data-action-id={item.id}>
    <button className="todo-complete" type="button" onClick={()=>onPrimary?.(item)} disabled={busy||!canRunPrimary(item)} aria-label={`${actionLabel}: ${item.title}`} title={actionLabel}><Icon name={item.kind==='routine'?(item.primary_action?.id==='reactivate'?'refresh':'history'):'check'} size={18}/></button>
    <a className="todo-row-main" href={item.deep_link||fallbackHref(item)}>
      <strong>{item.title}</strong>
      {metadata.length>0&&<span>{metadata.slice(0,2).join(' · ')}</span>}
    </a>
    {secondary.length?<details className="todo-actions-menu">
      <summary aria-label={`${text.actions}: ${item.title}`} title={text.actions}><Icon name="more" size={18}/></summary>
      <div className="todo-actions-popover" role="group" aria-label={`${text.actionOptions} ${item.title}`}>
        {secondary.map(action=>action.id==='snooze'?<button key={`${action.id}:${action.href}`} type="button" disabled={busy} onClick={event=>{event.currentTarget.closest('details')?.removeAttribute('open');onSecondary?.(item,action)}}><Icon name="history" size={16}/><span>{secondaryLabel(action,text)}</span></button>:<a key={`${action.id}:${action.href}`} href={linkFor(item,action)}><Icon name={action.id==='move'?'progress':'edit'} size={16}/><span>{secondaryLabel(action,text)}</span></a>)}
      </div>
    </details>:<a className="todo-overflow" href={item.deep_link||fallbackHref(item)} aria-label={`${text.open}: ${item.title}`}><Icon name="more" size={18}/></a>}
  </article>;
}
