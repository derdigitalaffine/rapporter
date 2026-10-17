import {Icon} from './icons';
import {formatDateTime} from './locale';
import {eventDayKeys,isWarningEvent,zonedDateKey} from './calendar-event-ui';
import {isWasteEvent} from './waste-ui';
import {useTodayCoreData} from './todayCoreData';
import './today-core-widgets.css';

const settledStates=new Set(['done','done_today','paused']);
const visibleAction=item=>item&&!settledStates.has(item.state);
const timeValue=value=>{const time=value?new Date(value).getTime():Number.POSITIVE_INFINITY;return Number.isFinite(time)?time:Number.POSITIVE_INFINITY};

function labels(language){
 const de=!String(language||'').startsWith('en');
 return de?{
  situation:'Lage heute',calm:'Heute ist alles im Plan',openOne:'1 offener Punkt heute',openMany:count=>`${count} offene Punkte heute`,next:'Als Nächstes',noConflicts:'Keine Überschneidungen',conflictOne:'1 Überschneidung',conflictMany:count=>`${count} Überschneidungen`,unavailable:'Die Tageslage ist gerade nur teilweise verfügbar',routineOne:'1 überfällige Routine',routineMany:count=>`${count} überfällige Routinen`,focusKicker:'JETZT WICHTIG',focus:'Top 3',focusEmpty:'Gerade nichts Dringendes',focusError:'Wichtige Punkte konnten gerade nicht vollständig geladen werden.',timelineKicker:'HEUTE',timeline:'Tagesverlauf',timelineEmpty:'Heute sind keine zeitgebundenen Punkte geplant.',timelineError:'Der Tagesverlauf ist gerade nur teilweise verfügbar.',allDay:'Ganztägig',task:'To-do',calendar:'Kalender',currentTime:'Jetzt',overdue:'Überfällig',due:'Heute fällig',high:'Hohe Priorität',active:'In Arbeit',waiting:'Wartet auf nächsten Schritt',warning:'Warnung',openTodo:'To-dos öffnen',openCalendar:'Kalender öffnen'
 }:{
  situation:'Today status',calm:'Everything is on track today',openOne:'1 open item today',openMany:count=>`${count} open items today`,next:'Up next',noConflicts:'No overlaps',conflictOne:'1 overlap',conflictMany:count=>`${count} overlaps`,unavailable:'Today status is only partially available right now',routineOne:'1 overdue routine',routineMany:count=>`${count} overdue routines`,focusKicker:'IMPORTANT NOW',focus:'Top 3',focusEmpty:'Nothing urgent right now',focusError:'Important items could not be loaded completely.',timelineKicker:'TODAY',timeline:'Day timeline',timelineEmpty:'No time-bound items are planned today.',timelineError:'The day timeline is only partially available right now.',allDay:'All day',task:'To-do',calendar:'Calendar',currentTime:'Now',overdue:'Overdue',due:'Due today',high:'High priority',active:'In progress',waiting:'Waiting for next step',warning:'Warning',openTodo:'Open to-dos',openCalendar:'Open calendar'
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

export function TodaySituation({family,language='de',widgetSize='compact',summaryOnly=false}){
 const core=useTodayCoreData(family);const l=labels(language);
 const actions=(core.actions||[]).filter(visibleAction);const overdue=actions.filter(item=>item.kind==='routine'&&item.state==='overdue');
 const timeline=timelineData(core,family,language);const next=timeline.timed.find(item=>timeValue(item.at)>=Date.now());const conflicts=conflictCount(core.events,family);
 const openLabel=actions.length===1?l.openOne:l.openMany(actions.length);const conflictLabel=conflicts===1?l.conflictOne:l.conflictMany(conflicts);const overdueLabel=overdue.length===1?l.routineOne:l.routineMany(overdue.length);
 const partial=core.actionFailed||core.calendarFailed;
 const calm=!core.loading&&!actions.length&&!conflicts&&!overdue.length&&!partial;
 const nextLabel=next?`${l.next} ${formatDateTime(language,new Date(next.at),{timeStyle:'short'})} · ${next.title}`:'';
 if(summaryOnly&&!partial&&!conflicts)return null;
 return <section className={`today-situation today-situation-${widgetSize}`} aria-label={l.situation} data-testid="today-situation" data-widget-size={widgetSize}>
  <div className="today-situation-signals">
   {!summaryOnly&&calm&&<span className="today-situation-signal today-situation-calm"><Icon name="doneAll"/><span>{l.calm}</span></span>}
   {!summaryOnly&&actions.length>0&&<a className="today-situation-signal" href="/?page=todo"><Icon name="tasks"/><span>{openLabel}</span></a>}
   {!summaryOnly&&next&&<a className="today-situation-signal" href={next.href}><Icon name="clock"/><span>{nextLabel}</span></a>}
   {(core.loaded&&!core.calendarFailed&&(!summaryOnly||conflicts>0))&&<a className={`today-situation-signal${conflicts?' has-alert':''}`} href="/?page=calendar"><Icon name={conflicts?'warning':'calendar'}/><span>{conflicts?conflictLabel:l.noConflicts}</span></a>}
   {!summaryOnly&&overdue.length>0&&<a className="today-situation-signal" href="/?page=todo"><Icon name="automation"/><span>{overdueLabel}</span></a>}
   {partial&&<span className="today-situation-signal has-alert" role="status"><Icon name="warning"/><span>{l.unavailable}</span></span>}
  </div>
 </section>;
}

export function TodayFocusWidget({family,language='de',compact=false}){
 const core=useTodayCoreData(family);const l=labels(language);const items=focusItems(core,family,language);
 return <section className="today-section today-focus" data-testid="today-focus"><div className="today-section-head"><div>{!compact&&<small>{l.focusKicker}</small>}<h2>{compact?(language.startsWith('de')?'Wichtig':'Important'):l.focus}</h2></div><a className="today-link" href="/?page=todo">{l.openTodo} <Icon name="next"/></a></div>
  {items.length?<ol className="today-focus-list">{items.map(item=><li key={item.key}><a href={item.href}><span className="today-focus-icon"><Icon name={item.icon}/></span><span className="grow"><strong>{item.title}</strong><small>{item.reason}</small></span><Icon name="next"/></a></li>)}</ol>:<div className="today-core-empty"><Icon name="doneAll"/><span>{core.loading?'…':l.focusEmpty}</span></div>}
  {(core.actionFailed||core.calendarFailed)&&<small className="today-core-status">{l.focusError}</small>}
 </section>;
}

export function TodayTimelineWidget({family,language='de'}){
 const core=useTodayCoreData(family);const l=labels(language);const timeline=timelineData(core,family,language);const now=new Date();const nowTime=now.getTime();const nowLabel=formatDateTime(language,now,{timeStyle:'short'});const nextIndex=timeline.timed.findIndex(item=>timeValue(item.at)>=nowTime);const nowIndex=nextIndex<0?timeline.timed.length:nextIndex;
 const rows=timeline.timed.length?Array.from({length:timeline.timed.length+1},(_,index)=>{
  if(index===nowIndex)return <li className="today-timeline-now" aria-label={`${l.currentTime} ${nowLabel}`} key="now"><time dateTime={now.toISOString()}>{nowLabel}</time><span className="today-timeline-now-dot" aria-hidden="true"/><strong>{l.currentTime}</strong></li>;
  const itemIndex=index>nowIndex?index-1:index;const item=timeline.timed[itemIndex];const past=timeValue(item.at)<nowTime;const next=itemIndex===nextIndex;const typeLabel=item.kind==='task'?l.task:l.calendar;const showSource=item.kind==='event'&&item.meta&&item.meta!==l.calendar;
  return <li key={item.key} className={['today-timeline-entry',`today-timeline-entry-${item.kind}`,past?'past':'',next?'next':''].filter(Boolean).join(' ')}><a href={item.href}><time dateTime={item.at}>{formatDateTime(language,new Date(item.at),{timeStyle:'short'})}</time><span className="today-timeline-dot" aria-hidden="true"/><span className="today-timeline-copy"><strong>{item.title}</strong><small className="today-timeline-meta"><span>{typeLabel}</span>{showSource&&<span>{item.meta}</span>}</small></span><Icon name="next"/></a></li>;
 }):[];
 return <section className="today-section today-timeline" data-testid="today-timeline"><div className="today-section-head"><div><small>{l.timelineKicker}</small><h2>{l.timeline}</h2></div><a className="today-link" href="/?page=calendar">{l.openCalendar} <Icon name="next"/></a></div>
  {timeline.allDay.length>0&&<div className="today-timeline-all-day"><span>{l.allDay}</span>{timeline.allDay.map(item=><a key={item.key} href={item.href}><strong>{item.title}</strong><small>{item.meta}</small></a>)}</div>}
  {timeline.timed.length?<ol className="today-timeline-list">{rows}</ol>:!timeline.allDay.length&&<div className="today-core-empty"><Icon name="calendar"/><span>{core.loading?'…':l.timelineEmpty}</span></div>}
  {(core.actionFailed||core.calendarFailed)&&<small className="today-core-status">{l.timelineError}</small>}
 </section>;
}
