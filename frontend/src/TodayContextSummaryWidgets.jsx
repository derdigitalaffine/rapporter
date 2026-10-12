import {Icon} from './icons';
import {formatDateTime} from './locale';
import {eventDayKeys,isWarningEvent,zonedDateKey} from './calendar-event-ui';
import {isWasteEvent} from './waste-ui';
import {useTodayCoreData} from './todayCoreData';
import {useTomorrowData} from './todayContextData';
import './today-context-summary-widgets.css';

const settledStates=new Set(['done','done_today','paused']);
const timeValue=value=>{const parsed=value?new Date(value).getTime():Number.POSITIVE_INFINITY;return Number.isFinite(parsed)?parsed:Number.POSITIVE_INFINITY};

const labels={
 de:{tomorrowKicker:'MORGEN',tomorrow:'Morgen',openCalendar:'Kalender öffnen',allDay:'Ganztägig',task:'To-do',calendar:'Kalender',empty:'Morgen ist nichts Zeitgebundenes geplant.',partial:'Morgen konnte gerade nur teilweise geladen werden.',more:count=>`+${count} weitere`,loadKicker:'FAMILIE',load:'Engpässe heute',conflict:'Terminüberschneidung',urgentOne:'1 dringendes Ding',urgentMany:count=>`${count} dringende Dinge`,calm:'Keine konkreten Engpässe erkannt.',partialLoad:'Engpässe konnten gerade nur teilweise geprüft werden.',overlaps:'überschneidet sich mit'},
 en:{tomorrowKicker:'TOMORROW',tomorrow:'Tomorrow',openCalendar:'Open calendar',allDay:'All day',task:'To-do',calendar:'Calendar',empty:'Nothing time-bound is planned for tomorrow.',partial:'Tomorrow could only be loaded partially.',more:count=>`+${count} more`,loadKicker:'FAMILY',load:'Today’s bottlenecks',conflict:'Calendar overlap',urgentOne:'1 urgent item',urgentMany:count=>`${count} urgent items`,calm:'No concrete bottlenecks detected.',partialLoad:'Bottlenecks could only be checked partially.',overlaps:'overlaps with'},
 fr:{tomorrowKicker:'DEMAIN',tomorrow:'Demain',openCalendar:'Ouvrir le calendrier',allDay:'Toute la journée',task:'Tâche',calendar:'Calendrier',empty:'Rien de prévu à une heure précise demain.',partial:'Les données de demain sont partiellement disponibles.',more:count=>`+${count} autres`,loadKicker:'FAMILLE',load:'Difficultés aujourd’hui',conflict:'Chevauchement de rendez-vous',urgentOne:'1 élément urgent',urgentMany:count=>`${count} éléments urgents`,calm:'Aucune difficulté concrète détectée.',partialLoad:'Les difficultés n’ont pu être vérifiées que partiellement.',overlaps:'chevauche'},
 nl:{tomorrowKicker:'MORGEN',tomorrow:'Morgen',openCalendar:'Kalender openen',allDay:'Hele dag',task:'Taak',calendar:'Kalender',empty:'Morgen staat niets tijdgebondens gepland.',partial:'Morgen kon slechts gedeeltelijk worden geladen.',more:count=>`+${count} meer`,loadKicker:'GEZIN',load:'Knelpunten vandaag',conflict:'Overlappende afspraken',urgentOne:'1 dringend item',urgentMany:count=>`${count} dringende items`,calm:'Geen concrete knelpunten gevonden.',partialLoad:'Knelpunten konden slechts gedeeltelijk worden gecontroleerd.',overlaps:'overlapt met'},
 th:{tomorrowKicker:'พรุ่งนี้',tomorrow:'พรุ่งนี้',openCalendar:'เปิดปฏิทิน',allDay:'ทั้งวัน',task:'งาน',calendar:'ปฏิทิน',empty:'พรุ่งนี้ไม่มีรายการที่กำหนดเวลาไว้',partial:'โหลดข้อมูลของพรุ่งนี้ได้เพียงบางส่วน',more:count=>`อีก ${count} รายการ`,loadKicker:'ครอบครัว',load:'สิ่งที่ต้องระวังวันนี้',conflict:'นัดหมายทับซ้อนกัน',urgentOne:'รายการเร่งด่วน 1 รายการ',urgentMany:count=>`รายการเร่งด่วน ${count} รายการ`,calm:'ไม่พบปัญหาที่ชัดเจน',partialLoad:'ตรวจสอบปัญหาได้เพียงบางส่วน',overlaps:'ทับซ้อนกับ'}
};
export function contextWidgetLabels(language){return labels[String(language||'de').toLowerCase().split('-')[0]]||labels.de}

function tomorrowRows(context,family,language){
 const l=contextWidgetLabels(language);const timeZone=family?.timezone||'UTC';const rows=[];
 (context.events||[]).forEach(event=>{
  if(!event||event.type==='weather.current'||isWarningEvent(event)||isWasteEvent(event)||event.type?.includes('weather'))return;
  const day=eventDayKeys(event,timeZone)[0]||context.day;
  rows.push({key:`event:${event.id}`,kind:'event',title:event.title||l.calendar,at:event.starts_at,allDay:Boolean(event.payload?.date_start&&!event.starts_at),href:`/?page=calendar&day=${encodeURIComponent(day)}`,meta:l.calendar});
 });
 (context.actions||[]).filter(item=>item&&!settledStates.has(item.state)).forEach(item=>rows.push({key:item.id,kind:'action',title:item.title,at:item.due_at||item.next_due_at,allDay:false,href:item.deep_link||'/?page=todo',meta:l.task}));
 rows.sort((a,b)=>Number(b.allDay)-Number(a.allDay)||timeValue(a.at)-timeValue(b.at)||a.title.localeCompare(b.title));
 return rows;
}

function todayEvents(events,family){
 const timeZone=family?.timezone||'UTC';const today=zonedDateKey(new Date(),timeZone);
 return (events||[]).filter(event=>event&&eventDayKeys(event,timeZone).includes(today));
}
function conflictPairs(events,family){
 const timed=todayEvents(events,family).filter(event=>event.starts_at&&event.ends_at&&!event.payload?.date_start&&!isWarningEvent(event)&&!isWasteEvent(event)&&!event.type?.includes('weather')).map(event=>({id:event.id,title:event.title,start:timeValue(event.starts_at),end:timeValue(event.ends_at)})).filter(row=>Number.isFinite(row.start)&&Number.isFinite(row.end)&&row.end>row.start).sort((a,b)=>a.start-b.start);
 const pairs=[];
 for(let i=0;i<timed.length;i+=1){for(let j=i+1;j<timed.length&&timed[j].start<timed[i].end;j+=1){if(timed[j].end>timed[i].start)pairs.push([timed[i],timed[j]])}}
 return pairs;
}

export function TodayTomorrowWidget({family,language='de',widgetSize='compact'}){
 const context=useTomorrowData(family);const l=contextWidgetLabels(language);const rows=tomorrowRows(context,family,language);const limit=widgetSize==='compact'?2:3;const shown=rows.slice(0,limit);const extra=Math.max(0,rows.length-shown.length);
 return <section className="today-section today-tomorrow" data-testid="today-tomorrow">
  <div className="today-section-head"><div><small>{l.tomorrowKicker}</small><h2>{l.tomorrow}</h2></div><a className="today-link" href="/?page=calendar">{l.openCalendar} <Icon name="next"/></a></div>
  {shown.length?<ol className="today-context-summary-list">{shown.map(row=><li key={row.key}><a href={row.href}><span className="today-context-summary-icon"><Icon name={row.kind==='action'?'check':'calendar'}/></span><span className="grow"><strong>{row.title}</strong><small>{row.allDay?l.allDay:row.at?`${formatDateTime(language,new Date(row.at),{timeStyle:'short',timeZone:family?.timezone||'UTC'})} · ${row.meta}`:row.meta}</small></span><Icon name="next"/></a></li>)}</ol>:<div className="today-core-empty"><Icon name="calendar"/><span>{context.loading?'…':l.empty}</span></div>}
  {extra>0&&<a className="today-context-summary-more" href="/?page=calendar">{l.more(extra)}</a>}
  {(context.actionFailed||context.calendarFailed)&&<small className="today-core-status">{l.partial}</small>}
 </section>;
}

export function TodayFamilyLoadWidget({family,language='de',widgetSize='compact'}){
 const core=useTodayCoreData(family);const l=contextWidgetLabels(language);const conflicts=conflictPairs(core.events,family);const urgent=(core.actions||[]).filter(item=>item&&!settledStates.has(item.state)&&(item.urgency==='critical'||item.urgency==='high'));const signals=[];
 conflicts.slice(0,widgetSize==='compact'?1:2).forEach(([left,right])=>signals.push({key:`conflict:${left.id}:${right.id}`,icon:'calendar',title:l.conflict,detail:`${left.title} ${l.overlaps} ${right.title}`,href:'/?page=calendar'}));
 if(urgent.length)signals.push({key:'urgent',icon:'priority',title:urgent.length===1?l.urgentOne:l.urgentMany(urgent.length),detail:'',href:'/?page=todo'});
 const shown=signals.slice(0,widgetSize==='compact'?2:3);
 return <section className="today-section today-family-load" data-testid="today-family-load">
  <div className="today-section-head"><div><small>{l.loadKicker}</small><h2>{l.load}</h2></div></div>
  {shown.length?<ol className="today-context-summary-list">{shown.map(signal=><li key={signal.key}><a href={signal.href}><span className="today-context-summary-icon"><Icon name={signal.icon}/></span><span className="grow"><strong>{signal.title}</strong>{signal.detail&&<small>{signal.detail}</small>}</span><Icon name="next"/></a></li>)}</ol>:<div className="today-core-empty"><Icon name="doneAll"/><span>{core.loading?'…':l.calm}</span></div>}
  {(core.actionFailed||core.calendarFailed)&&<small className="today-core-status">{l.partialLoad}</small>}
 </section>;
}
