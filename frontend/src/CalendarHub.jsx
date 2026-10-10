import {useEffect,useMemo,useState} from 'react';
import i18n from './i18n';
import './calendar-i18n';
import './birthday-i18n';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {formatDateTime} from './locale';
import {isWasteEvent,wasteClass,wasteKind,wasteKindLabel} from './waste-ui';
import {eventDayKeys,isHolidayEvent,isNativeCalendarEvent,zonedDateKey} from './calendar-event-ui';
import {CALENDAR_COLORS,CALENDAR_ICONS,memberDescriptor,sourceDescriptor,sourceIdentity} from './calendar-source-ui';
import {useFamilyPermissions} from './family-permissions';
import EventEditor from './EventEditor';
import './calendar-hub.css';

const unwrap=value=>value?.results||value||[];
const VIEW_VALUES=['week','month','list'];

export default function CalendarHub({family,onBack,t}){
 const targetDay=new URLSearchParams(window.location.search).get('day');
 const timeZone=family?.timezone||'Europe/Berlin';
 const today=zonedDateKey(new Date(),timeZone);
 const [events,setEvents]=useState([]);
 const [sources,setSources]=useState([]);
 const [view,setView]=useState('week');
 const [anchor,setAnchor]=useState(targetDay||today);
 const [selectedDay,setSelectedDay]=useState(targetDay||today);
 const [hiddenSources,setHiddenSources]=useState(()=>new Set());
 const [detail,setDetail]=useState(null);
 const [edit,setEdit]=useState(null);
 const [showPast,setShowPast]=useState(Boolean(targetDay&&targetDay<today));
 const [sourceSettings,setSourceSettings]=useState(false);
 const {permissions,canManageSettings}=useFamilyPermissions(family);
 const language=i18n.language;

 const load=async()=>{
  const [eventData,sourceData]=await Promise.all([api('/events/'),api('/integrations/')]);
  setEvents(unwrap(eventData).filter(item=>!family||String(item.family)===String(family.id)).sort((a,b)=>eventTime(a)-eventTime(b)));
  setSources(unwrap(sourceData).filter(item=>!family||String(item.family)===String(family.id)));
 };
 useEffect(()=>{load().catch(error=>toast(error.message||t('saveFailed'),{type:'error'}))},[family?.id]);

 const sourceOptions=useMemo(()=>{
  const map=new Map();
  events.forEach(event=>{const id=sourceIdentity(event);if(!map.has(id))map.set(id,sourceDescriptor(event,sources,family,t))});
  return [...map.values()];
 },[events,sources,family?.id,language]);
 const visibleEvents=useMemo(()=>events.filter(event=>!hiddenSources.has(sourceIdentity(event))),[events,hiddenSources]);
 const periodEvents=useMemo(()=>visibleEvents,[visibleEvents]);
 const weekDays=useMemo(()=>weekKeys(anchor),[anchor]);
 const monthDays=useMemo(()=>monthGrid(anchor),[anchor]);
 const listEvents=useMemo(()=>showPast?periodEvents:periodEvents.filter(event=>!eventIsPast(event)),[periodEvents,showPast]);
 const grouped=useMemo(()=>groupByDay(listEvents,timeZone),[listEvents,timeZone]);
 const hasPast=useMemo(()=>periodEvents.some(eventIsPast),[periodEvents]);

 function toggleSource(id){setHiddenSources(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next})}
 function selectDay(day){setSelectedDay(day);setAnchor(day)}
 function movePeriod(direction){
  if(view==='month'){const next=addMonths(anchor,direction);setAnchor(next);setSelectedDay(next);return}
  const next=addDays(anchor,direction*7);setAnchor(next);setSelectedDay(next);
 }
 function goToday(){setAnchor(today);setSelectedDay(today);setShowPast(false)}
 function changeView(next){if(VIEW_VALUES.includes(next))setView(next)}
 function openEvent(event){if(event.type==='birthday'&&event.payload?.url){window.location.assign(event.payload.url);return}setDetail(event)}
 const dayEvents=day=>eventsForDay(periodEvents,day,timeZone);

 return <div className="smart-page calendar-shell">
  <div className="page-head calendar-page-head">
   <button className="back-button" onClick={onBack} aria-label={t('back')}><Icon name="back"/></button>
   <div className="grow"><small>{t('calendarUi.familyCalendar')}</small><h1>{t('calendar')}</h1></div>
   {permissions.createContent&&<button className="primary compact calendar-add" onClick={()=>setEdit({})}><Icon name="plus"/>{t('calendarUi.newEvent')}</button>}
  </div>
  <p className="page-intro">{t('calendarUi.calendarIntro')}</p>

  <section className="calendar-commandbar" aria-label={t('calendarUi.calendarControls')}>
   <div className="calendar-period-nav">
    <button className="calendar-icon-button" onClick={()=>movePeriod(-1)} aria-label={t('calendarUi.previousPeriod')}><Icon name="back"/></button>
    <button className={`secondary compact calendar-today ${anchor===today?'is-current':''}`} onClick={goToday}>{t('calendarUi.today')}</button>
    <button className="calendar-icon-button" onClick={()=>movePeriod(1)} aria-label={t('calendarUi.nextPeriod')}><Icon name="next"/></button>
    <div className="calendar-period-title"><strong>{periodTitle(view,anchor,language)}</strong><span>{view==='week'?weekNumberLabel(anchor,t,language):t(`calendarUi.view${capitalize(view)}`)}</span></div>
   </div>
   <div className="calendar-view-switch" role="group" aria-label={t('calendarUi.chooseView')}>
    {VIEW_VALUES.map(value=><button key={value} aria-pressed={view===value} className={view===value?'active':''} onClick={()=>changeView(value)}>{t(`calendarUi.view${capitalize(value)}`)}</button>)}
   </div>
  </section>

  {sourceOptions.length>0&&<section className="calendar-sourcebar" aria-label={t('calendarUi.sources')}>
   <button className={`calendar-source-chip ${hiddenSources.size===0?'active':''}`} onClick={()=>setHiddenSources(new Set())}><Icon name="calendar"/><span>{t('all')}</span></button>
   {sourceOptions.map(source=><button key={source.id} className={`calendar-source-chip tone-${source.color} ${hiddenSources.has(source.id)?'muted':'active'}`} aria-pressed={!hiddenSources.has(source.id)} onClick={()=>toggleSource(source.id)}><span className="calendar-source-dot"/><Icon name={source.icon}/><span>{source.name}</span></button>)}
   {canManageSettings&&sourceOptions.some(item=>item.configurable)&&<button className="calendar-source-settings" onClick={()=>setSourceSettings(true)}><Icon name="sliders"/>{t('calendarUi.customizeSources')}</button>}
  </section>}

  {view==='week'&&<WeekView days={weekDays} selectedDay={selectedDay} today={today} eventsForDay={dayEvents} onSelectDay={selectDay} onOpen={openEvent} sources={sources} family={family} t={t} language={language}/>} 
  {view==='month'&&<MonthView days={monthDays} anchor={anchor} selectedDay={selectedDay} today={today} eventsForDay={dayEvents} onSelectDay={selectDay} onOpen={openEvent} sources={sources} family={family} t={t} language={language}/>} 
  {view==='list'&&<ListView grouped={grouped} targetDay={targetDay} hasPast={hasPast} showPast={showPast} onTogglePast={()=>setShowPast(value=>!value)} onOpen={openEvent} sources={sources} family={family} t={t} language={language}/>} 

  {detail&&<EventDetail event={detail} sources={sources} family={family} t={t} language={language} onClose={()=>setDetail(null)} onEdit={isNativeCalendarEvent(detail)?()=>{setDetail(null);setEdit(detail)}:null}/>} 
  {edit!==null&&<EventEditor family={family} event={edit?.id?edit:null} onClose={()=>setEdit(null)} onSaved={async()=>{setEdit(null);await load()}}/>}
  {sourceSettings&&<SourceAppearanceSheet sources={sourceOptions.filter(item=>item.configurable)} t={t} onClose={()=>setSourceSettings(false)} onSaved={async()=>{setSourceSettings(false);await load()}}/>}
 </div>
}

function WeekView({days,selectedDay,today,eventsForDay,onSelectDay,onOpen,sources,family,t,language}){
 return <section className="calendar-view calendar-week-view" aria-label={t('calendarUi.viewWeek')}>
  <div className="calendar-week-grid">{days.map(day=><article key={day} className={`calendar-week-day ${day===today?'is-today':''} ${day===selectedDay?'is-selected':''}`}><button className="calendar-day-head" onClick={()=>onSelectDay(day)} aria-current={day===today?'date':undefined}><span>{weekdayLabel(day,language,'short')}</span><strong>{Number(day.slice(-2))}</strong></button><div className="calendar-day-events">{eventsForDay(day).length?eventsForDay(day).map(event=><EventChip key={`${event.id}-${day}`} event={event} sources={sources} family={family} t={t} language={language} onOpen={()=>onOpen(event)}/>):<span className="calendar-day-empty">{t('calendarUi.free')}</span>}</div></article>)}</div>
  <div className="calendar-week-mobile"><div className="calendar-mobile-daystrip">{days.map(day=><button key={day} className={`${day===selectedDay?'active':''} ${day===today?'is-today':''}`} aria-current={day===today?'date':undefined} onClick={()=>onSelectDay(day)}><span>{weekdayLabel(day,language,'narrow')}</span><strong>{Number(day.slice(-2))}</strong><i>{eventsForDay(day).length||''}</i></button>)}</div><DayAgenda day={selectedDay} events={eventsForDay(selectedDay)} onOpen={onOpen} sources={sources} family={family} t={t} language={language}/></div>
 </section>
}

function MonthView({days,anchor,selectedDay,today,eventsForDay,onSelectDay,onOpen,sources,family,t,language}){
 const month=anchor.slice(0,7);
 return <section className="calendar-view calendar-month-view" aria-label={t('calendarUi.viewMonth')}>
  <div className="calendar-month-weekdays" aria-hidden="true">{weekKeys('2026-06-01').map(day=><span key={day}>{weekdayLabel(day,language,'short')}</span>)}</div>
  <div className="calendar-month-grid">{days.map(day=>{const events=eventsForDay(day);return <article key={day} className={`calendar-month-day ${day.slice(0,7)!==month?'outside':''} ${day===today?'is-today':''} ${day===selectedDay?'is-selected':''}`}><button className="calendar-month-date" onClick={()=>onSelectDay(day)} aria-label={longDayLabel(day,language)} aria-current={day===today?'date':undefined}>{Number(day.slice(-2))}</button><div className="calendar-month-events">{events.slice(0,3).map(event=><EventChip compact key={`${event.id}-${day}`} event={event} sources={sources} family={family} t={t} language={language} onOpen={()=>onOpen(event)}/>)}{events.length>3&&<button className="calendar-more" onClick={()=>onSelectDay(day)}>+{events.length-3}</button>}</div></article>})}</div>
  <DayAgenda day={selectedDay} events={eventsForDay(selectedDay)} onOpen={onOpen} sources={sources} family={family} t={t} language={language}/>
 </section>
}

function DayAgenda({day,events,onOpen,sources,family,t,language}){
 return <section className="calendar-selected-day"><div className="calendar-selected-day-head"><div><small>{weekdayLabel(day,language,'long')}</small><h2>{dayMonthLabel(day,language)}</h2></div><span>{events.length}</span></div>{events.length?<div className="agenda-list">{events.map(event=><CalendarEventRow key={event.id} event={event} sources={sources} family={family} t={t} language={language} onOpen={()=>onOpen(event)}/>)}</div>:<div className="calendar-day-empty-state"><Icon name="calendar"/><span>{t('calendarUi.noEventsThisDay')}</span></div>}</section>
}

function ListView({grouped,targetDay,hasPast,showPast,onTogglePast,onOpen,sources,family,t,language}){
 useEffect(()=>{if(!targetDay)return;const timer=setTimeout(()=>document.getElementById(`calendar-day-${targetDay}`)?.scrollIntoView({block:'start',behavior:'smooth'}),50);return()=>clearTimeout(timer)},[targetDay,grouped.length]);
 return <section className="calendar-view calendar-list-view">{hasPast&&<div className="calendar-history-toggle"><button className="secondary compact" aria-pressed={showPast} onClick={onTogglePast}><Icon name="calendar"/>{t(showPast?'calendarUi.hidePast':'calendarUi.showPast')}</button></div>}<div className="agenda-days">{grouped.length?grouped.map(([day,rows])=><section className={`agenda-day ${targetDay===day?'agenda-day-target':''}`} id={`calendar-day-${day}`} key={day}><div className="agenda-day-head"><div><small>{dayRelativeLabel(day,t,language)}</small><h2>{dayMonthLabel(day,language)}</h2></div><span>{rows.length}</span></div><div className="agenda-list">{rows.map(event=><CalendarEventRow key={event.id} event={event} sources={sources} family={family} t={t} language={language} onOpen={()=>onOpen(event)}/>)}</div></section>):<div className="smart-empty"><Icon name="calendar" size={34}/><strong>{t('noUpcoming')}</strong><span>{t('calendarAddHint')}</span></div>}</div></section>
}

function CalendarEventRow(props){if(isHolidayEvent(props.event))return <HolidayEvent {...props}/>;if(isWasteEvent(props.event))return <WasteEvent {...props}/>;return <AgendaEvent {...props}/>}

function HolidayEvent({event,sources,family,t,language,onOpen}){
 const source=sourceDescriptor(event,sources,family,t);const de=language.startsWith('de');
 return <button className="agenda-special agenda-holiday" onClick={onOpen}><span className="special-rail" aria-hidden="true"/><span className="agenda-special-icon"><Icon name="school"/></span><div className="grow"><div className="agenda-special-label">{de?'FERIEN':'SCHOOL HOLIDAY'}</div><strong>{event.title}</strong><span>{formatHolidayRange(event,t,language)}</span></div><span className="agenda-special-source"><Icon name={source.icon}/>{source.name}</span><Icon name="next" className="agenda-affordance"/></button>
}

function WasteEvent({event,sources,family,t,language,onOpen}){
 const source=sourceDescriptor(event,sources,family,t);const kind=wasteKind(event);const tone=wasteClass(event);const de=language.startsWith('de');
 return <button className={`agenda-special agenda-waste ${tone}`} onClick={onOpen}><span className={`waste-dot ${tone}`} aria-hidden="true"><Icon name="waste" size={8}/></span><span className="agenda-special-icon"><Icon name="waste"/></span><div className="grow"><div className="agenda-special-label">{de?'MÜLLABFUHR':'WASTE COLLECTION'}</div><strong>{event.title}</strong><span>{wasteKindLabel(kind,language)}{event.payload?.location?` · ${event.payload.location}`:''}</span></div><span className={`agenda-special-source ${tone}`}><Icon name={source.icon}/>{source.name}</span><Icon name="next" className="agenda-affordance"/></button>
}

function EventChip({event,sources,family,t,language,onOpen,compact=false}){
 const source=sourceDescriptor(event,sources,family,t);const member=memberDescriptor(event,family);
 return <button className={`calendar-event-chip tone-${source.color} ${compact?'compact':''}`} onClick={onOpen} title={event.title}><Icon name={source.icon}/><span className="calendar-event-chip-text">{event.payload?.all_day?'':`${formatTime(event.starts_at,language)} `}{event.title}</span>{member&&<span className="calendar-member-mark" title={member.name}><Icon name="user"/></span>}</button>
}

function AgendaEvent({event,sources,family,t,language,onOpen}){
 const source=sourceDescriptor(event,sources,family,t);const member=memberDescriptor(event,family);const recurring=event.payload?.recurring||event.payload?.recurrence;
 return <button className="agenda-event" onClick={onOpen}><div className="agenda-time">{event.payload?.all_day?<strong>{t('calendarUi.allDay')}</strong>:<><strong>{formatTime(event.starts_at,language)}</strong>{event.ends_at&&<span>{formatEndTime(event,language)}</span>}</>}</div><span className={`agenda-source-icon tone-${source.color}`}><Icon name={source.icon}/></span><div className="grow agenda-event-main"><div className="agenda-title-line"><strong>{event.title}</strong>{event.payload?.delay_minutes>0&&<span className="delay-badge">+{event.payload.delay_minutes} min</span>}</div><div className="agenda-event-meta">{event.payload?.location&&<span><Icon name="location"/>{event.payload.location}</span>}<span className={`source-badge tone-${source.color}`}><Icon name={source.icon}/>{source.name}</span>{member&&<span className="member-badge"><Icon name="user"/>{member.name}</span>}{recurring&&<span><Icon name="refresh"/>{t('calendarUi.recurring')}</span>}</div></div><Icon name={isNativeCalendarEvent(event)?'edit':'next'} className="agenda-affordance"/></button>
}

function EventDetail({event,sources,family,t,language,onClose,onEdit}){
 const source=sourceDescriptor(event,sources,family,t);const member=memberDescriptor(event,family);const provider=isNativeCalendarEvent(event)?'FamilyOS':source.name;const recurring=event.payload?.recurring||event.payload?.recurrence;const special=isHolidayEvent(event)?'holiday-detail':isWasteEvent(event)?'waste-detail':'';const sourceUrl=safeHttpsUrl(event.payload?.source_url);
 return <div className="sheet-backdrop" onMouseDown={eventMouse=>eventMouse.target===eventMouse.currentTarget&&onClose()}><section className={`quick-sheet calendar-detail ${special}`} role="dialog" aria-modal="true" aria-labelledby="calendar-detail-title"><div className="sheet-handle"/><div className="sheet-head"><div><span className={`source-badge tone-${source.color}`}><Icon name={source.icon}/>{source.name}</span><h2 id="calendar-detail-title">{event.title}</h2></div><button className="sheet-close" onClick={onClose} aria-label={t('back')}><Icon name="close"/></button></div><div className="event-detail-body"><div className="event-detail-primary"><span className={`agenda-source-icon tone-${source.color}`}><Icon name={source.icon}/></span><div><strong>{formatFullDate(event,t,language)}</strong><span>{formatEventRange(event,t,language)}</span></div></div>{event.payload?.location&&<DetailRow icon="location" label={t('location')} value={event.payload.location}/>} {event.payload?.description&&<DetailRow icon="info" label={t('notes')} value={event.payload.description}/>} {member&&<DetailRow icon="user" label={t('calendarUi.person')} value={member.name}/>} {recurring&&<DetailRow icon="refresh" label={t('recurrence')} value={t('calendarUi.recurring')}/>}<DetailRow icon="integrations" label={t('calendarUi.source')} value={provider}/>{sourceUrl&&<a className="text-link" href={sourceUrl} target="_blank" rel="noreferrer"><Icon name="link"/>{t('calendarUi.officialSource')}</a>}</div>{onEdit?<button className="primary" onClick={onEdit}><Icon name="edit"/>{t('editEvent')}</button>:<div className="readonly-event-note"><Icon name="info"/><span>{t('calendarUi.readonly')}</span></div>}</section></div>
}

function SourceAppearanceSheet({sources,t,onClose,onSaved}){
 const [draft,setDraft]=useState(()=>Object.fromEntries(sources.map(item=>[item.sourceId,{color:item.color,icon:item.icon}])));const [saving,setSaving]=useState(false);
 async function save(){setSaving(true);try{for(const source of sources){const value=draft[source.sourceId];await api(`/calendar-sources/${source.sourceId}/appearance/`,{method:'PATCH',body:JSON.stringify(value)})}toast(t('calendarUi.appearanceSaved'),{type:'success'});await onSaved()}catch(error){toast(error.message||t('saveFailed'),{type:'error'});setSaving(false)}}
 return <div className="sheet-backdrop" onMouseDown={event=>event.target===event.currentTarget&&onClose()}><section className="quick-sheet calendar-source-sheet" role="dialog" aria-modal="true"><div className="sheet-handle"/><div className="sheet-head"><div><small>{t('calendarUi.sources')}</small><h2>{t('calendarUi.customizeSources')}</h2></div><button className="sheet-close" onClick={onClose} aria-label={t('back')}><Icon name="close"/></button></div><div className="calendar-source-editor">{sources.map(source=><div className="calendar-source-editor-row" key={source.sourceId}><div className={`calendar-source-preview tone-${draft[source.sourceId]?.color||source.color}`}><Icon name={draft[source.sourceId]?.icon||source.icon}/><strong>{source.name}</strong></div><label><span>{t('calendarUi.color')}</span><select value={draft[source.sourceId]?.color||source.color} onChange={event=>setDraft(current=>({...current,[source.sourceId]:{...current[source.sourceId],color:event.target.value}}))}>{CALENDAR_COLORS.map(color=><option key={color} value={color}>{t(`calendarUi.color_${color}`)}</option>)}</select></label><label><span>{t('calendarUi.symbol')}</span><select value={draft[source.sourceId]?.icon||source.icon} onChange={event=>setDraft(current=>({...current,[source.sourceId]:{...current[source.sourceId],icon:event.target.value}}))}>{CALENDAR_ICONS.map(icon=><option key={icon} value={icon}>{t(`calendarUi.icon_${icon}`)}</option>)}</select></label></div>)}</div><button className="primary" disabled={saving} onClick={save}><Icon name="check"/>{saving?t('saving'):t('save')}</button></section></div>
}

function DetailRow({icon,label,value}){return <div className="event-detail-row"><Icon name={icon}/><div><small>{label}</small><span>{value}</span></div></div>}
function capitalize(value){return value.charAt(0).toUpperCase()+value.slice(1)}
function localDay(key){const [year,month,day]=String(key).split('-').map(Number);return new Date(year,month-1,day,12)}
function dateKey(date){return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`}
function addDays(key,amount){const date=localDay(key);date.setDate(date.getDate()+amount);return dateKey(date)}
function addMonths(key,amount){const date=localDay(key);const wanted=date.getDate();date.setDate(1);date.setMonth(date.getMonth()+amount);date.setDate(Math.min(wanted,new Date(date.getFullYear(),date.getMonth()+1,0).getDate()));return dateKey(date)}
function weekKeys(anchor){const date=localDay(anchor);const offset=(date.getDay()+6)%7;date.setDate(date.getDate()-offset);return Array.from({length:7},(_,index)=>{const next=new Date(date);next.setDate(date.getDate()+index);return dateKey(next)})}
function monthGrid(anchor){const first=`${anchor.slice(0,7)}-01`;const start=weekKeys(first)[0];return Array.from({length:42},(_,index)=>addDays(start,index))}
function weekNumberLabel(anchor,t,language){const date=localDay(weekKeys(anchor)[0]);date.setDate(date.getDate()+3);const first=new Date(date.getFullYear(),0,4,12);const firstMonday=weekKeys(dateKey(first))[0];const week=1+Math.round((localDay(dateKey(date))-localDay(firstMonday))/604800000);return language.startsWith('de')?`KW ${week}`:`${t('calendarUi.week')} ${week}`}
function periodTitle(view,anchor,language){if(view==='month'||view==='list')return formatDateTime(language,localDay(anchor),{month:'long',year:'numeric'});const days=weekKeys(anchor);const first=localDay(days[0]),last=localDay(days[6]);if(first.getMonth()===last.getMonth())return `${first.getDate()}.–${last.getDate()}. ${formatDateTime(language,last,{month:'long',year:'numeric'})}`;return `${formatDateTime(language,first,{day:'numeric',month:'short'})} – ${formatDateTime(language,last,{day:'numeric',month:'short',year:'numeric'})}`}
function weekdayLabel(key,language,width='short'){return formatDateTime(language,localDay(key),{weekday:width})}
function dayMonthLabel(key,language){return formatDateTime(language,localDay(key),{day:'numeric',month:'long'})}
function longDayLabel(key,language){return formatDateTime(language,localDay(key),{weekday:'long',day:'numeric',month:'long',year:'numeric'})}
function eventTime(event){return event.starts_at?new Date(event.starts_at).getTime():Number.MAX_SAFE_INTEGER}
function eventIsPast(event){if(!event.starts_at)return false;return new Date(event.ends_at||event.starts_at).getTime()<Date.now()}
function eventsForDay(events,day,timeZone){return events.filter(event=>eventDayKeys(event,timeZone).includes(day)).sort((a,b)=>eventTime(a)-eventTime(b))}
function groupByDay(events,timeZone){const groups=new Map();events.forEach(event=>{const key=event.payload?.date_start||zonedDateKey(event.starts_at,timeZone)||'undated';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(event)});return [...groups.entries()].sort(([a],[b])=>a.localeCompare(b))}
function dayRelativeLabel(key,t,language){if(key==='undated')return t('calendarUi.undatedUpper');const today=dateKey(new Date());const diff=Math.round((localDay(key)-localDay(today))/86400000);if(diff===0)return t('calendarUi.todayUpper');if(diff===1)return t('calendarUi.tomorrowUpper');if(diff===-1)return t('calendarUi.yesterdayUpper');return weekdayLabel(key,language,'long').toUpperCase()}
function formatTime(value,language){return value?formatDateTime(language,value,{hour:'2-digit',minute:'2-digit'}):'–'}
function formatEndTime(event,language){if(!event.ends_at)return'';const start=event.starts_at?new Date(event.starts_at):null,end=new Date(event.ends_at);if(start&&start.toDateString()!==end.toDateString())return formatDateTime(language,end,{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});return `– ${formatTime(event.ends_at,language)}`}
function formatFullDate(event,t,language){if(!event.starts_at&&!event.payload?.date_start)return t('calendarUi.noDate');return formatDateTime(language,event.payload?.date_start?localDay(event.payload.date_start):event.starts_at,{weekday:'long',day:'numeric',month:'long',year:'numeric'})}
function formatHolidayRange(event,t,language){const start=event.payload?.date_start,end=event.payload?.date_end_exclusive;if(!start)return formatFullDate(event,t,language);if(!end)return dayMonthLabel(start,language);const last=addDays(end,-1);return last===start?dayMonthLabel(start,language):`${dayMonthLabel(start,language)} – ${dayMonthLabel(last,language)}`}
function formatEventRange(event,t,language){if(event.payload?.all_day){const start=event.payload.date_start,end=event.payload.date_end_exclusive;if(start&&end&&addDays(end,-1)!==start)return `${dayMonthLabel(start,language)} – ${formatDateTime(language,localDay(addDays(end,-1)),{day:'numeric',month:'long',year:'numeric'})} · ${t('calendarUi.allDay')}`;return t('calendarUi.allDay')}if(!event.starts_at)return'';return `${formatTime(event.starts_at,language)}${event.ends_at?` ${formatEndTime(event,language)}`:''}`}
function safeHttpsUrl(value){try{const url=new URL(String(value||''));return url.protocol==='https:'?url.href:''}catch{return''}}
