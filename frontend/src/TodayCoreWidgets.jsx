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
  situation:'Lage heute',calm:'Alles ruhig',openOne:'1 Ding heute offen',openMany:count=>`${count} Dinge heute offen`,next:'Als Nächstes',noConflicts:'keine Konflikte',conflictOne:'1 Überschneidung',conflictMany:count=>`${count} Überschneidungen`,unavailable:'Lage gerade nur teilweise verfügbar',focusKicker:'JETZT WICHTIG',focus:'Top 3',focusEmpty:'Gerade nichts Dringendes',focusError:'Wichtige Punkte konnten gerade nicht vollständig geladen werden.',timelineKicker:'HEUTE',timeline:'Tagesverlauf',timelineEmpty:'Heute sind keine zeitgebundenen Punkte geplant.',timelineError:'Der Tagesverlauf ist gerade nur teilweise verfügbar.',allDay:'Ganztägig',task:'To-do',calendar:'Kalender',currentTime:'Jetzt',overdue:'Überfällig',due:'Heute fällig',high:'Hohe Priorität',active:'In Arbeit',waiting:'Wartet auf nächsten Schritt',warning:'Warnung',openTodo:'To-dos öffnen',openCalendar:'Kalender öffnen'
 }:{
  situation:'Today at a glance',calm:'All quiet',openOne:'1 thing open today',openMany:count=>`${count} things open today`,next:'Up next',noConflicts:'no conflicts',conflictOne:'1 overlap',conflictMany:count=>`${count} overlaps`,unavailable:'Today is only partially available right now',focusKicker:'IMPORTANT NOW',focus:'Top 3',focusEmpty:'Nothing urgent right now',focusError:'Important items could not be loaded completely.',timelineKicker:'TODAY',timeline:'Day timeline',timelineEmpty:'No time-bound items are planned today.',timelineError:'The day timeline is only partially available right now.',allDay:'All day',task:'To-do',calendar:'Calendar',currentTime:'Now',overdue:'Overdue',due:'Due today',high:'High priority',active:'In progress',waiting:'Waiting for next step',warning:'Warning',openTodo:'Open to-dos',openCalendar:'Open calendar'
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
 const actions=(core.actions||[]).filter(item=>visibleAction(item)&&(item.urgency==='critical'||item.urgency==='high'||Number(item.ranking?.bucket)<=4)).map(item=>({key:item.id,title:item.title,reason:focusReason(item,l),rank:Number.isFinite(Number(item.ranking?.bucket))?Number(item.ranking.bucket):5,at:item.due_at||item.next_due_at,href:item.deep_link||'/?page=todo',icon:item.kind==='routine'?'routine':'check'}));
 return [...warnings,...actions].sort((a,b)=>a.rank-b.rank||timeValue(a.at)-timeValue(b.at)||a.title.localeCompare(b.title)).slice(0,3);
}

export function TodaySituation({family,language='de'}){
 const core=useTodayCoreData(family);const l=labels(language);const actions=(core.actions||[]).filter(visibleAction);const timeline=timelineData(core,family,language);const next=timeline.timed.find(item=>timeValue(item.at)>=Date.now());const conflicts=conflictCount(core.events,family);const facts=[];
 if(actions.length)facts.push({key:'open',label:actions.length===1?l.openOne:l.openMany(actions.length),href:'/?page=todo'});
 if(next)facts.push({key:'next',label:`${l.next}: ${formatDateTime(language,new Date(next.at),{timeStyle:'short'})} · ${next.title}`,href:next.href});
 if(conflicts)facts.push({key:'conflicts',label:conflicts===1?l.conflictOne:l.conflictMany(conflicts),href:'/?page=calendar'});else if(core.loaded&&!core.calendarFailed)facts.push({key:'conflicts',label:l.noConflicts,href:'/?page=calendar'});
 const visibleFacts=facts.slice(0,3);
 return <nav className="today-situation" aria-label={l.situation} data-testid="today-situation">
  <span className="today-situation-label">{l.situation}</span>
  <div className="today-situation-facts">{visibleFacts.length?visibleFacts.map(fact=><a key={fact.key} href={fact.href}>{fact.label}</a>):<span>{core.loading?'…':l.calm}</span>}</div>
  {(core.actionFailed||core.calendarFailed)&&<span className="today-situation-status">{l.unavailable}</span>}
 </nav>;
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
