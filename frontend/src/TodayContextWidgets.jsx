import {useEffect,useMemo,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {currentWeek,eventDayKeys,eventMarker,eventVisibleInWeek,isoWeekNumber,isHolidayEvent} from './calendar-event-ui';
import './today-context-widgets.css';

const unwrap=value=>value?.results||value||[];
const defaultWeekSettings={events:true,waste:true,holidays:true,special:true};

export function WeekCompassWidget({family,language='de',settings=defaultWeekSettings,compact=false}){
 const [events,setEvents]=useState([]);const [failed,setFailed]=useState(false);const [weekOffset,setWeekOffset]=useState(0);
 const de=language.startsWith('de');const timeZone=family?.timezone||'Europe/Berlin';
 useEffect(()=>{let current=true;setFailed(false);api('/events/').then(result=>{if(current)setEvents(unwrap(result).filter(row=>String(row.family)===String(family.id)))}).catch(()=>{if(current){setEvents([]);setFailed(true)}});return()=>{current=false}},[family.id]);
 useEffect(()=>setWeekOffset(0),[family.id,timeZone]);
 const currentDays=useMemo(()=>currentWeek(timeZone),[timeZone]);
 const currentDayKey=currentDays.find(day=>day.current)?.key||'';
 const days=useMemo(()=>{
  if(weekOffset===0)return currentDays;
  const anchor=new Date(currentDays[0].date);anchor.setUTCDate(anchor.getUTCDate()+(weekOffset*7)+2);
  return currentWeek(timeZone,anchor).map(day=>({...day,current:day.key===currentDayKey}));
 },[currentDays,currentDayKey,timeZone,weekOffset]);
 const byDay=useMemo(()=>{const map=new Map(days.map(day=>[day.key,[]]));for(const event of events){if(!eventVisibleInWeek(event,{...defaultWeekSettings,...settings}))continue;for(const key of eventDayKeys(event,timeZone)){if(map.has(key))map.get(key).push(event)}}return map},[days,events,timeZone,settings?.events,settings?.waste,settings?.holidays,settings?.special]);
 const week=isoWeekNumber(days[0].date);const formatter=new Intl.DateTimeFormat(de?'de-DE':'en-GB',{timeZone:'UTC',weekday:'short',day:'numeric'});
 return <section className={`today-section week-compass ${compact?'week-compass-compact':''}`} data-testid="week-compass"><div className="today-section-head"><div><small>{de?'WOCHENKOMPASS':'WEEK COMPASS'}</small><h2>{de?`Kalenderwoche ${week}`:`Week ${week}`}</h2></div><div className="week-compass-head-actions">{weekOffset!==0&&<button className="today-link" onClick={()=>setWeekOffset(0)}>{de?'Heute':'Today'}</button>}<button className="today-link" onClick={()=>window.location.assign('/?page=calendar')}>{de?'Kalender':'Calendar'} <Icon name="next"/></button></div></div>
 <div className="week-compass-strip"><button className="week-compass-nav" onClick={()=>setWeekOffset(value=>value-1)} aria-label={de?'Vorherige Woche':'Previous week'}><Icon name="back"/></button><ol className="week-compass-days" aria-label={de?`Kalenderwoche ${week}`:`Week ${week}`}>{days.map(day=>{const rows=byDay.get(day.key)||[];const holiday=rows.find(isHolidayEvent);const visible=rows.slice(0,compact?2:3);const hidden=Math.max(0,rows.length-visible.length);const parts=formatter.formatToParts(day.date);const weekday=parts.find(part=>part.type==='weekday')?.value?.replace('.','')||'';const number=parts.find(part=>part.type==='day')?.value||'';const description=rows.length?rows.map(event=>event.title).join(', '):(de?'Keine Ereignisse':'No events');return <li key={day.key} className={`${day.current?'current ':''}${holiday?'has-holiday':''}`}><button onClick={()=>window.location.assign(`/?page=calendar&day=${day.key}`)} aria-current={day.current?'date':undefined} aria-label={`${weekday} ${number}. ${description}`}><span className="week-day-name">{weekday}</span><strong>{number}</strong>{holiday&&<span className="week-holiday-mark" aria-hidden="true"><Icon name="school" size={9}/></span>}<span className="week-markers" aria-hidden="true">{visible.map((event,index)=>{const marker=eventMarker(event);return <i key={`${event.id}-${index}`} className={`week-marker ${marker.className}`}><Icon name={marker.icon} size={7}/></i>})}{hidden>0&&<em>+{hidden}</em>}</span></button></li>})}</ol><button className="week-compass-nav" onClick={()=>setWeekOffset(value=>value+1)} aria-label={de?'Nächste Woche':'Next week'}><Icon name="next"/></button></div>
 {failed&&<small className="week-widget-status">{de?'Kalenderdaten konnten gerade nicht geladen werden.':'Calendar data could not be loaded.'}</small>}</section>
}

export function PinboardTodayWidget({family,language='de',compact=false}){
 const [pins,setPins]=useState([]);const [loading,setLoading]=useState(true);const de=language.startsWith('de');
 useEffect(()=>{let current=true;setLoading(true);api(`/board/?family=${encodeURIComponent(family.id)}`).then(result=>{if(current)setPins(unwrap(result).slice(0,compact?2:4))}).catch(()=>{if(current)setPins([])}).finally(()=>{if(current)setLoading(false)});return()=>{current=false}},[family.id,compact]);
 return <section className="today-section today-pinboard" data-testid="today-pinboard"><div className="today-section-head"><div><small>{de?'GEMEINSAM IM BLICK':'SHARED AT A GLANCE'}</small><h2>{de?'Pinnwand':'Pinboard'}</h2></div><button className="today-link" onClick={()=>window.location.assign('/?page=board')}>{de?'Öffnen':'Open'} <Icon name="next"/></button></div>
 {pins.length?<div className="today-pinboard-grid">{pins.map(pin=><PinPreview key={pin.id} pin={pin} de={de}/>)}</div>:<button className="today-pinboard-empty" onClick={()=>window.location.assign('/?page=board&compose=1')}><span><Icon name="plus"/></span><strong>{loading?(de?'Pinnwand wird geladen …':'Loading pinboard …'):(de?'Ersten wichtigen Punkt anpinnen':'Pin the first important item')}</strong><small>{de?'Notiz, Foto, Termin, Aufgabe oder Einkauf':'Note, photo, event, task or shopping'}</small></button>}
 <div className="today-pinboard-actions"><button className="secondary compact" onClick={()=>window.location.assign('/?page=board&compose=1')}><Icon name="plus"/> {de?'Anpinnen':'Pin something'}</button></div></section>
}

function PinPreview({pin,de}){
 const target=pin.target;const unavailable=target?.available===false;const href=target?.url||`/?page=board&post=${encodeURIComponent(pin.id)}`;const title=unavailable?(de?'Nicht mehr verfügbar':'No longer available'):(target?.title||pin.text||typeLabel(pin.kind,de));const meta=unavailable?'':target?.subtitle||pin.author_name||'';return <button className={`today-pin ${pin.kind||'note'} ${unavailable?'unavailable':''}`} onClick={()=>window.location.assign(href)}>{pin.images?.[0]&&<img src={pin.images[0].url} alt="" width={pin.images[0].width} height={pin.images[0].height} loading="lazy"/>}<span className="today-pin-type"><Icon name={pinIcon(pin.kind)}/></span><span className="today-pin-copy"><strong>{String(title).slice(0,100)}</strong>{meta&&<small>{formatMeta(meta,de)}</small>}</span></button>
}

function pinIcon(kind){return kind==='event'?'calendar':kind==='task'?'tasks':kind==='shopping'?'shopping':kind==='photo'?'camera':'lists'}
function typeLabel(kind,de){const labels=de?{note:'Notizzettel',photo:'Foto',event:'Termin',task:'Aufgabe',note_ref:'Notiz',shopping:'Einkauf'}:{note:'Note',photo:'Photo',event:'Event',task:'Task',note_ref:'Note',shopping:'Shopping'};return labels[kind]||labels.note}
function formatMeta(value,de){if(!value)return'';if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}T/.test(value)){const date=new Date(value);if(!Number.isNaN(date.getTime()))return date.toLocaleString(de?'de-DE':'en-GB',{dateStyle:'short',timeStyle:'short'})}return String(value).slice(0,120)}
