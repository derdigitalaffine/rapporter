import {useState} from 'react';
import {Icon} from './icons';
import {formatDateTime} from './locale';
import {eventDayKeys,isWarningEvent,zonedDateKey} from './calendar-event-ui';
import {isWasteEvent} from './waste-ui';
import {useTodayCoreData} from './todayCoreData';
import {runTodoPrimary} from './todo-action-runner';
import './today-core-widgets.css';

const settledStates=new Set(['done','done_today','paused']);
const visibleAction=item=>item&&!settledStates.has(item.state);
const timeValue=value=>{const time=value?new Date(value).getTime():Number.POSITIVE_INFINITY;return Number.isFinite(time)?time:Number.POSITIVE_INFINITY};

function labels(language){
 const de=!String(language||'').startsWith('en');
 return de?{
  situation:'Lage heute',calm:'Heute ist alles im Plan',openOne:'1 offener Punkt heute',openMany:count=>`${count} offene Punkte heute`,next:'Als Nächstes',noConflicts:'Keine Überschneidungen',conflictOne:'1 Überschneidung',conflictMany:count=>`${count} Überschneidungen`,unavailable:'Die Tageslage ist gerade nur teilweise verfügbar',routineOne:'1 überfällige Routine',routineMany:count=>`${count} überfällige Routinen`,completeRoutine:title=>`Erledigen: ${title}`,workingRoutine:title=>`Wird erledigt: ${title}`,undoRoutine:title=>`Rückgängig: ${title}`,routineFailed:'Die Routine konnte nicht erledigt werden.',undoFailed:'Die Routine konnte nicht wiederhergestellt werden.',moreRoutines:count=>`${count} weitere überfällige Routinen öffnen`,focusKicker:'JETZT WICHTIG',focus:'Top 3',focusEmpty:'Gerade nichts Dringendes',focusError:'Wichtige Punkte konnten gerade nicht vollständig geladen werden.',timelineKicker:'HEUTE',timeline:'Tagesverlauf',timelineEmpty:'Heute sind keine zeitgebundenen Punkte geplant.',timelineError:'Der Tagesverlauf ist gerade nur teilweise verfügbar.',allDay:'Ganztägig',task:'To-do',calendar:'Kalender',currentTime:'Jetzt',overdue:'Überfällig',due:'Heute fällig',high:'Hohe Priorität',active:'In Arbeit',waiting:'Wartet auf nächsten Schritt',warning:'Warnung',openTodo:'To-dos öffnen',openCalendar:'Kalender öffnen'
 }:{
  situation:'Today status',calm:'Everything is on track today',openOne:'1 open item today',openMany:count=>`${count} open items today`,next:'Up next',noConflicts:'No overlaps',conflictOne:'1 overlap',conflictMany:count=>`${count} overlaps`,unavailable:'Today status is only partially available right now',routineOne:'1 overdue routine',routineMany:count=>`${count} overdue routines`,completeRoutine:title=>`Complete: ${title}`,workingRoutine:title=>`Completing: ${title}`,undoRoutine:title=>`Undo: ${title}`,routineFailed:'The routine could not be completed.',undoFailed:'The routine could not be restored.',moreRoutines:count=>`Open ${count} more overdue routines`,focusKicker:'IMPORTANT NOW',focus:'Top 3',focusEmpty:'Nothing urgent right now',focusError:'Important items could not be loaded completely.',timelineKicker:'TODAY',timeline:'Day timeline',timelineEmpty:'No time-bound items are planned today.',timelineError:'The day timeline is only partially available right now.',allDay:'All day',task:'To-do',calendar:'Calendar',currentTime:'Now',overdue:'Overdue',due:'Due today',high:'High priority',active:'In progress',waiting:'Waiting for next step',warning:'Warning',openTodo:'Open to-dos',openCalendar:'Open calendar'
 };
}

function todayEvents(events,family){
 const timeZone=family?.timezone||'UTC';const day=zonedDateKey(new Date(),timeZone);
 return (events||[]).filter(event=>event&&event.type!=='weather.current'&&eventDayKeys(event,timeZone).includes(day));
}
function localClock(value,timeZone){
 if(!value)return null;const date=new Date(value);if(Number.isNaN(date.getTime()))return null;
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date);
 const read=type=>Number(parts.find(part=>part.type===type)?.value||0);return {hour:read('hour'),minute:read('minute')};
}
function timedTask(item,family){
 if(item?.kind!=='task'||!item.due_at||!visibleAction(item))return false;
 const timeZone=family?.timezone||'UTC';
 if(zonedDateKey(item.due_at,timeZone)!==zonedDateKey(new Date(),timeZone))return false;
 const clock=localClock(item.due_at,timeZone);
 return Boolean(clock&&(clock.hour!==0||clock.minute!==0));
}
function timelineData(core,family,language){
 const l=labels(language);const rows=todayEvents(core.events,family);const allDay=[];const timed=[];
 rows.forEach(event=>{
  if(isWarningEvent(event)||isWasteEvent(event)||event.type?.includes('weather'))return;
  const href=`/?page=calendar&day=${encodeURIComponent(eventDayKeys(event,family?.timezone||'UTC')[0]||'')}`;
  const row={key:`event:${event.id}`,kind:'event',title:event.title||l.calendar,at:event.starts_at,endsAt:event.ends_at,href,meta:event.source_meta?.presentation?.label||event.source_meta?.name||l.calendar};
  if(event.payload?.date_start)allDay.push(row);else if(event.starts_at)timed.push(row);
 });
 (core.actions||[]).filter(item=>timedTask(item,family)).forEach(item=>timed.push({key:item.id,kind:'task',title:item.title,at:item.due_at,endsAt:null,href:item.deep_link||'/?page=todo',meta:l.task}));
 timed.sort((a,b)=>timeValue(a.at)-timeValue(b.at)||a.title.localeCompare(b.title));
 return {allDay,timed};
}
function conflictCount(events,family){
 const timed=todayEvents(events,family).filter(event=>event.starts_at&&event.ends_at&&!event.payload?.date_start&&!isWarningEvent(event)&&!isWasteEvent(event)&&!event.type?.includes('weather')).map(event=>({start:timeValue(event.starts_at),end:timeValue(event.ends_at)})).filter(row=>Number.isFinite(row.start)&&Number.isFinite(row.end)&&row.end>row.start).sort((a,b)=>a.start-b.start);
 let conflicts=0;for(let i=0;i<timed.length;i+=1){for(let j=i+1;j<timed.length&&timed[j].start<timed[i].end;j+=1){if(timed[j].end>timed[i].start)conflicts+=1}}return conflicts;
}
function focusReason(item,l){
 if(item.state==='overdue')return l.overdue;if(item.state==='due')return l.due;if(item.priority==='high')return l.high;if(item.state==='active')return l.active;if(item.state==='waiting')return l.waiting;return l.due;
}
function focusItems(core,family,language){
 const l=labels(language);const warnings=todayEvents(core.events,family).filter(isWarningEvent).map(event=>({key:`warning:${event.id}`,title:event.title,reason:l.warning,rank:-1,at:event.starts_at,href:`/?page=calendar&day=${encodeURIComponent(eventDayKeys(event,family?.timezone||'UTC')[0]||'')}`,icon:'warning'}));
 const actions=(core.actions||[]).filter(item=>visibleAction(item)&&(item.urgency==='critical'||item.urgency==='high'||Number(item.ranking?.bucket)<=4)).map(item=>({key:item.id,title:item.title,reason:focusReason(item,l),rank:Number.isFinite(Number(item.ranking?.bucket))?Number(item.ranking.bucket):5,at:item.due_at||item.next_due_at,href:item.deep_link||'/?page=todo',icon:item.kind==='routine'?'automation':'check'}));
 return [...warnings,...actions].sort((a,b)=>a.rank-b.rank||timeValue(a.at)-timeValue(b.at)||a.title.localeCompare(b.title)).slice(0,3);
}

export function TodaySituation({family,language='de',widgetSize='compact'}){
 const core=useTodayCoreData(family);const l=labels(language);const [busyId,setBusyId]=useState('');const [undoState,setUndoState]=useState(null);const [actionError,setActionError]=useState('');
 const actions=(core.actions||[]).filter(visibleAction);const overdue=actions.filter(item=>item.kind==='routine'&&item.state==='overdue'&&item.primary_action?.id==='record_done'&&item.primary_action?.method==='POST');
 const timeline=timelineData(core,family,language);const next=timeline.timed.find(item=>timeValue(item.at)>=Date.now());const conflicts=conflictCount(core.events,family);const maxRoutineActions=widgetSize==='medium'?4:2;const visibleRoutines=overdue.slice(0,maxRoutineActions);const hiddenRoutineCount=Math.max(0,overdue.length-visibleRoutines.length);
 const openLabel=actions.length===1?l.openOne:l.openMany(actions.length);const conflictLabel=conflicts===1?l.conflictOne:l.conflictMany(conflicts);const overdueLabel=overdue.length===1?l.routineOne:l.routineMany(overdue.length);
 const finishRoutine=async item=>{
  if(busyId)return;setBusyId(item.id);setActionError('');
  try{const result=await runTodoPrimary(item);setUndoState(result?.undo?{title:item.title,undo:result.undo}:null);await core.refresh()}
  catch{setActionError(l.routineFailed)}finally{setBusyId('')}
 };
 const undoRoutine=async()=>{
  if(!undoState||busyId)return;setBusyId('undo');setActionError('');
  try{await undoState.undo();setUndoState(null);await core.refresh()}
  catch{setActionError(l.undoFailed)}finally{setBusyId('')}
 };
 const calm=!core.loading&&!actions.length&&!conflicts&&!overdue.length;
 return <section className={`today-situation today-situation-${widgetSize}`} aria-label={l.situation} data-testid="today-situation" data-widget-size={widgetSize}>
  <div className="today-situation-signals">
   {calm&&<span className="today-situation-signal today-situation-calm" role="img" aria-label={l.calm} title={l.calm}><Icon name="doneAll"/></span>}
   {actions.length>0&&<a className="today-situation-signal" href="/?page=todo" aria-label={openLabel} title={openLabel}><Icon name="tasks"/><span className="today-situation-badge" aria-hidden="true">{actions.length}</span></a>}
   {next&&<a className="today-situation-signal" href={next.href} aria-label={`${l.next}: ${formatDateTime(language,new Date(next.at),{timeStyle:'short'})} · ${next.title}`} title={`${l.next}: ${formatDateTime(language,new Date(next.at),{timeStyle:'short'})} · ${next.title}`}><Icon name="clock"/></a>}
   {(core.loaded&&!core.calendarFailed)&&<a className={`today-situation-signal${conflicts?' has-alert':''}`} href="/?page=calendar" aria-label={conflicts?conflictLabel:l.noConflicts} title={conflicts?conflictLabel:l.noConflicts}><Icon name={conflicts?'warning':'calendar'}/>{conflicts>0&&<span className="today-situation-badge" aria-hidden="true">{conflicts}</span>}</a>}
   {visibleRoutines.map(item=>{const label=busyId===item.id?l.workingRoutine(item.title):l.completeRoutine(item.title);return <button key={item.id} type="button" className="today-situation-signal today-situation-routine" aria-label={label} title={`${overdueLabel} · ${l.completeRoutine(item.title)}`} onClick={()=>finishRoutine(item)} disabled={Boolean(busyId)}><Icon name="automation"/><span className="today-situation-check" aria-hidden="true"><Icon name="check" size={10}/></span></button>})}
   {hiddenRoutineCount>0&&<a className="today-situation-signal today-situation-more" href="/?page=todo" aria-label={l.moreRoutines(hiddenRoutineCount)} title={l.moreRoutines(hiddenRoutineCount)}><Icon name="more"/><span className="today-situation-badge" aria-hidden="true">{hiddenRoutineCount}</span></a>}
   {undoState&&<button type="button" className="today-situation-signal today-situation-undo" aria-label={l.undoRoutine(undoState.title)} title={l.undoRoutine(undoState.title)} onClick={undoRoutine} disabled={Boolean(busyId)}><Icon name="refresh"/></button>}
   {(core.actionFailed||core.calendarFailed||actionError)&&<span className="today-situation-signal has-alert" role="img" aria-label={actionError||l.unavailable} title={actionError||l.unavailable}><Icon name="warning"/></span>}
  </div>
  <span className="today-situation-sr-only" role="status" aria-live="polite">{actionError||((core.actionFailed||core.calendarFailed)?l.unavailable:'')}</span>
 </section>;
}

export function TodayFocusWidget({family,language='de'}){
 const core=useTodayCoreData(family);const l=labels(language);const items=focusItems(core,family,language);
 return <section className="today-section today-focus" data-testid="today-focus"><div className="today-section-head"><div><small>{l.focusKicker}</small><h2>{l.focus}</h2></div><a className="today-link" href="/?page=todo">{l.openTodo} <Icon name="next"/></a></div>
  {items.length?<ol className="today-focus-list">{items.map(item=><li key={item.key}><a href={item.href}><span className="today-focus-icon"><Icon name={item.icon}/></span><span className="grow"><strong>{item.title}</strong><small>{item.reason}</small></span><Icon name="next"/></a></li>)}</ol>:<div className="today-core-empty"><Icon name="doneAll"/><span>{core.loading?'…':l.focusEmpty}</span></div>}
  {(core.actionFailed||core.calendarFailed)&&<small className="today-core-status">{l.focusError}</small>}
 </section>;
}

export function TodayTimelineWidget({family,language='de'}){
 const core=useTodayCoreData(family);const l=labels(language);const timeline=timelineData(core,family,language);const nowLabel=formatDateTime(language,new Date(),{timeStyle:'short'});
 return <section className="today-section today-timeline" data-testid="today-timeline"><div className="today-section-head"><div><small>{l.timelineKicker}</small><h2>{l.timeline}</h2></div><a className="today-link" href="/?page=calendar">{l.openCalendar} <Icon name="next"/></a></div>
  {timeline.allDay.length>0&&<div className="today-timeline-all-day"><span>{l.allDay}</span>{timeline.allDay.map(item=><a key={item.key} href={item.href}><strong>{item.title}</strong><small>{item.meta}</small></a>)}</div>}
  {timeline.timed.length?<ol className="today-timeline-list">{timeline.timed.map(item=>{const past=timeValue(item.at)<Date.now();return <li key={item.key} className={past?'past':''}><a href={item.href}><time dateTime={item.at}>{formatDateTime(language,new Date(item.at),{timeStyle:'short'})}</time><span className="today-timeline-dot" aria-hidden="true"/><span className="grow"><strong>{item.title}</strong><small>{item.meta}</small></span><Icon name="next"/></a></li>})}</ol>:!timeline.allDay.length&&<div className="today-core-empty"><Icon name="calendar"/><span>{core.loading?'…':l.timelineEmpty}</span></div>}
  <div className="today-timeline-now" aria-label={`${l.currentTime} ${nowLabel}`}><span/>{l.currentTime} · {nowLabel}</div>
  {(core.actionFailed||core.calendarFailed)&&<small className="today-core-status">{l.timelineError}</small>}
 </section>;
}
