import {useEffect,useMemo,useState} from 'react';
import {Icon} from './icons';
import {formatDateTime} from './locale';
import {eventDayKeys,eventMarker,eventSourceDescriptor,eventSourceStyle,isoWeekNumber,isHolidayEvent,zonedDateKey} from './calendar-event-ui';
import './calendar-v2.css';
import './calendar-markers.css';

const VIEW_VALUES=['week','month','list'];

export function calendarViewFromLocation(){
 const value=new URLSearchParams(window.location.search).get('view');
 return VIEW_VALUES.includes(value)?value:'week';
}

export default function CalendarPresentation({view,onViewChange,onRangeChange,events,family,t,language,onOpen,targetDay,listContent}){
 const timeZone=family?.timezone||'Europe/Berlin';
 const today=zonedDateKey(new Date(),timeZone);
 const [anchor,setAnchor]=useState(targetDay||today);
 const [selectedDay,setSelectedDay]=useState(targetDay||today);
 useEffect(()=>{if(targetDay){setAnchor(targetDay);setSelectedDay(targetDay)}},[targetDay]);
 const weekDays=useMemo(()=>weekKeys(anchor),[anchor]);
 const monthDays=useMemo(()=>monthGrid(anchor),[anchor]);
 const visibleRange=useMemo(()=>rangeForView(view,anchor),[view,anchor]);
 useEffect(()=>{onRangeChange?.(visibleRange)},[onRangeChange,visibleRange]);
 const eventsFor=day=>eventsForDay(events,day,timeZone);
 function movePeriod(direction){
  if(view==='month'){const next=addMonths(anchor,direction);setAnchor(next);setSelectedDay(next);return}
  const next=addDays(anchor,direction*7);setAnchor(next);setSelectedDay(next);
 }
 function goToday(){setAnchor(today);setSelectedDay(today)}
 return <>
  <section className="calendar-commandbar" aria-label={t('calendarUi.calendarControls')}>
   <div className="calendar-period-nav">
    {view!=='list'&&<button className="calendar-icon-button" onClick={()=>movePeriod(-1)} aria-label={t('calendarUi.previousPeriod')}><Icon name="back"/></button>}
    <button className={`secondary compact calendar-today ${anchor===today?'is-current':''}`} onClick={goToday}>{t('calendarUi.today')}</button>
    {view!=='list'&&<button className="calendar-icon-button" onClick={()=>movePeriod(1)} aria-label={t('calendarUi.nextPeriod')}><Icon name="next"/></button>}
    <div className="calendar-period-title"><strong>{periodTitle(view,anchor,language)}</strong>{view==='week'&&<span>{weekLabel(anchor,t)}</span>}</div>
   </div>
   <div className="calendar-view-switch" role="group" aria-label={t('calendarUi.chooseView')}>
    {VIEW_VALUES.map(value=><button key={value} aria-pressed={view===value} className={view===value?'active':''} onClick={()=>onViewChange(value)}>{t(`calendarUi.view${capitalize(value)}`)}</button>)}
   </div>
  </section>
  {view==='week'&&<WeekView days={weekDays} selectedDay={selectedDay} today={today} eventsFor={eventsFor} onSelect={day=>{setSelectedDay(day);setAnchor(day)}} onOpen={onOpen} t={t} language={language}/>} 
  {view==='month'&&<MonthView days={monthDays} anchor={anchor} selectedDay={selectedDay} today={today} eventsFor={eventsFor} onSelect={day=>{setSelectedDay(day);setAnchor(day)}} onOpen={onOpen} t={t} language={language}/>} 
  {view==='list'&&listContent}
 </>
}

function WeekView({days,selectedDay,today,eventsFor,onSelect,onOpen,t,language}){
 return <section className="calendar-view calendar-week-view" aria-label={t('calendarUi.viewWeek')}>
  <div className="calendar-week-grid">{days.map(day=>{const rows=eventsFor(day);const holiday=rows.some(isHolidayEvent);return <article key={day} className={`calendar-week-day ${day===today?'is-today':''} ${day===selectedDay?'is-selected':''} ${holiday?'has-holiday':''}`}><button className="calendar-day-head" onClick={()=>onSelect(day)} aria-current={day===today?'date':undefined}><span>{weekdayLabel(day,language,'short')}</span><strong>{Number(day.slice(-2))}</strong></button><div className="calendar-day-events">{rows.length?rows.slice(0,5).map(event=><EventChip key={`${event.id}-${day}`} event={event} onOpen={()=>onOpen(event)} t={t} language={language}/>):<span className="calendar-day-empty">{t('calendarUi.free')}</span>}{rows.length>5&&<button className="calendar-more" onClick={()=>onSelect(day)}>+{rows.length-5}</button>}</div></article>})}</div>
  <div className="calendar-week-mobile"><div className="calendar-mobile-daystrip">{days.map(day=>{const rows=eventsFor(day);const holiday=rows.find(isHolidayEvent);const markerRows=rows.filter(event=>!isHolidayEvent(event));const visible=markerRows.slice(0,3);const hidden=Math.max(0,markerRows.length-visible.length);const description=rows.map(event=>event.title).join(', ');return <button key={day} className={`${day===selectedDay?'active':''} ${day===today?'is-today':''} ${holiday?'has-holiday':''}`} aria-current={day===today?'date':undefined} aria-label={`${longDayLabel(day,language)}${description?`. ${description}`:''}`} onClick={()=>onSelect(day)}><span className="calendar-mobile-weekday">{weekdayLabel(day,language,'narrow')}</span><strong>{Number(day.slice(-2))}</strong>{holiday&&<span className="calendar-mobile-holiday-mark" aria-hidden="true"><Icon name="school" size={8}/></span>}<span className="calendar-mobile-markers" aria-hidden="true">{visible.map((event,index)=>{const marker=eventMarker(event);return <i key={`${event.id}-${index}`} className={`calendar-mobile-marker ${marker.className}`}><Icon name={marker.icon} size={6}/></i>})}{hidden>0&&<em>+{hidden}</em>}</span></button>})}</div></div>
  <SelectedDay day={selectedDay} events={eventsFor(selectedDay)} onOpen={onOpen} t={t} language={language}/>
 </section>
}

function MonthView({days,anchor,selectedDay,today,eventsFor,onSelect,onOpen,t,language}){
 const month=anchor.slice(0,7);
 return <section className="calendar-view calendar-month-view" aria-label={t('calendarUi.viewMonth')}>
  <div className="calendar-month-weekdays" aria-hidden="true">{weekKeys('2026-06-01').map(day=><span key={day}>{weekdayLabel(day,language,'short')}</span>)}</div>
  <div className="calendar-month-grid">{days.map(day=>{const rows=eventsFor(day);const holiday=rows.some(isHolidayEvent);return <article key={day} className={`calendar-month-day ${day.slice(0,7)!==month?'outside':''} ${day===today?'is-today':''} ${day===selectedDay?'is-selected':''} ${holiday?'has-holiday':''}`}><button className="calendar-month-date" onClick={()=>onSelect(day)} aria-label={longDayLabel(day,language)} aria-current={day===today?'date':undefined}>{Number(day.slice(-2))}</button><div className="calendar-month-events">{rows.slice(0,3).map(event=><EventChip compact key={`${event.id}-${day}`} event={event} onOpen={()=>onOpen(event)} t={t} language={language}/>)}{rows.length>3&&<button className="calendar-more" onClick={()=>onSelect(day)}>+{rows.length-3}</button>}</div></article>})}</div>
  <SelectedDay day={selectedDay} events={eventsFor(selectedDay)} onOpen={onOpen} t={t} language={language}/>
 </section>
}

function SelectedDay({day,events,onOpen,t,language}){
 return <section className="calendar-selected-day"><div className="calendar-selected-day-head"><div><small>{weekdayLabel(day,language,'long')}</small><h2>{dayMonthLabel(day,language)}</h2></div><span>{events.length}</span></div>{events.length?<div className="calendar-selected-events">{events.map(event=><EventChip key={event.id} event={event} onOpen={()=>onOpen(event)} t={t} language={language}/>)}</div>:<div className="calendar-day-empty-state"><Icon name="calendar"/><span>{t('calendarUi.noEventsThisDay')}</span></div>}</section>
}

function EventChip({event,onOpen,t,language,compact=false}){
 const source=eventSourceDescriptor(event,t);const holiday=isHolidayEvent(event);
 return <button className={`calendar-event-chip source-${source.key} ${holiday?'calendar-holiday-chip':''} ${compact?'compact':''}`} style={eventSourceStyle(event)} onClick={onOpen} title={`${source.label}: ${event.title}`}><Icon name={source.icon}/><span className="calendar-event-chip-text">{event.payload?.all_day?'':`${formatTime(event.starts_at,language)} `}{event.title}</span>{event.payload?.all_day&&<small>{t('calendarUi.allDay')}</small>}</button>
}

function parseDay(key){const [year,month,day]=String(key).split('-').map(Number);return new Date(Date.UTC(year,month-1,day,12))}
function keyFor(date){return `${date.getUTCFullYear()}-${String(date.getUTCMonth()+1).padStart(2,'0')}-${String(date.getUTCDate()).padStart(2,'0')}`}
function addDays(key,amount){const date=parseDay(key);date.setUTCDate(date.getUTCDate()+amount);return keyFor(date)}
function addMonths(key,amount){const date=parseDay(key);date.setUTCDate(1);date.setUTCMonth(date.getUTCMonth()+amount);return keyFor(date)}
function weekKeys(anchor){const date=parseDay(anchor);const offset=(date.getUTCDay()+6)%7;date.setUTCDate(date.getUTCDate()-offset);return Array.from({length:7},(_,index)=>{const value=new Date(date);value.setUTCDate(date.getUTCDate()+index);return keyFor(value)})}
function monthGrid(anchor){const date=parseDay(anchor);const first=`${date.getUTCFullYear()}-${String(date.getUTCMonth()+1).padStart(2,'0')}-01`;const start=weekKeys(first)[0];return Array.from({length:42},(_,index)=>addDays(start,index))}
function rangeForView(view,anchor){if(view==='list')return {includeUndated:true};if(view==='month'){const days=monthGrid(anchor);return {start:days[0],end:days[days.length-1]}}const days=weekKeys(anchor);return {start:days[0],end:days[days.length-1]}}
function eventsForDay(events,day,timeZone){return events.filter(event=>eventDayKeys(event,timeZone).includes(day))}
function periodTitle(view,anchor,language){if(view==='list')return language.startsWith('de')?'Alle Termine':'All events';if(view==='month')return formatDateTime(language,parseDay(anchor),{month:'long',year:'numeric'});const days=weekKeys(anchor);const first=parseDay(days[0]),last=parseDay(days[6]);return `${formatDateTime(language,first,{day:'numeric',month:'short'})} – ${formatDateTime(language,last,{day:'numeric',month:'short',year:'numeric'})}`}
function weekLabel(anchor,t){return `${t('calendarUi.week')} ${isoWeekNumber(parseDay(weekKeys(anchor)[0]))}`}
function weekdayLabel(day,language,width){return formatDateTime(language,parseDay(day),{weekday:width})}
function longDayLabel(day,language){return formatDateTime(language,parseDay(day),{weekday:'long',day:'numeric',month:'long',year:'numeric'})}
function dayMonthLabel(day,language){return formatDateTime(language,parseDay(day),{day:'numeric',month:'long'})}
function formatTime(value,language){return value?formatDateTime(language,value,{hour:'2-digit',minute:'2-digit'}):'–'}
function capitalize(value){return value.charAt(0).toUpperCase()+value.slice(1)}
