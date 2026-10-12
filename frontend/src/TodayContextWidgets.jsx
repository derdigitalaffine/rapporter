import {useEffect,useMemo,useRef,useState} from 'react';
import {api,AUTH_CHANGED_EVENT} from './api';
import PinInteractionBar from './PinInteractions';
import {Icon} from './icons';
import {currentWeek,eventDayKeys,eventMarker,eventVisibleInWeek,isoWeekNumber,isHolidayEvent} from './calendar-event-ui';
import {fetchCalendarEvents} from './calendar-events-api';
import {formatPinEventMeta,pinAuthorHue,pinAuthorInitial,pinIconName,pinTypeLabel} from './pinboard-ui';
import './today-context-widgets.css';

const unwrap=value=>value?.results||value||[];
const defaultWeekSettings={events:true,waste:true,holidays:true,special:true};

export function WeekCompassWidget({family,language='de',settings=defaultWeekSettings,compact=false}){
 const [events,setEvents]=useState([]);const [failed,setFailed]=useState(false);const [weekOffset,setWeekOffset]=useState(0);
 const de=language.startsWith('de');const timeZone=family?.timezone||'Europe/Berlin';
 useEffect(()=>setWeekOffset(0),[family.id,timeZone]);
 const currentDays=useMemo(()=>currentWeek(timeZone),[timeZone]);
 const currentDayKey=currentDays.find(day=>day.current)?.key||'';
 const days=useMemo(()=>{
  if(weekOffset===0)return currentDays;
  const anchor=new Date(currentDays[0].date);anchor.setUTCDate(anchor.getUTCDate()+(weekOffset*7)+2);
  return currentWeek(timeZone,anchor).map(day=>({...day,current:day.key===currentDayKey}));
 },[currentDays,currentDayKey,timeZone,weekOffset]);
 const windowStart=days[0]?.key;const windowEnd=days[days.length-1]?.key;
 useEffect(()=>{let current=true;setFailed(false);fetchCalendarEvents({familyId:family.id,start:windowStart,end:windowEnd}).then(result=>{if(current)setEvents(result.filter(row=>String(row.family)===String(family.id)))}).catch(()=>{if(current){setEvents([]);setFailed(true)}});return()=>{current=false}},[family.id,windowStart,windowEnd]);
 const byDay=useMemo(()=>{const map=new Map(days.map(day=>[day.key,[]]));for(const event of events){if(!eventVisibleInWeek(event,{...defaultWeekSettings,...settings}))continue;for(const key of eventDayKeys(event,timeZone)){if(map.has(key))map.get(key).push(event)}}return map},[days,events,timeZone,settings?.events,settings?.waste,settings?.holidays,settings?.special]);
 const week=isoWeekNumber(days[0].date);const formatter=new Intl.DateTimeFormat(de?'de-DE':'en-GB',{timeZone:'UTC',weekday:'short',day:'numeric'});
 return <section className={`today-section week-compass ${compact?'week-compass-compact':''}`} data-testid="week-compass"><div className="today-section-head"><div><small>{de?'WOCHENKOMPASS':'WEEK COMPASS'}</small><h2>{de?`Kalenderwoche ${week}`:`Week ${week}`}</h2></div><div className="week-compass-head-actions">{weekOffset!==0&&<button className="today-link" onClick={()=>setWeekOffset(0)}>{de?'Heute':'Today'}</button>}<button className="today-link" onClick={()=>window.location.assign('/?page=calendar')}>{de?'Kalender':'Calendar'} <Icon name="next"/></button></div></div>
 <div className="week-compass-strip"><button className="week-compass-nav" onClick={()=>setWeekOffset(value=>value-1)} aria-label={de?'Vorherige Woche':'Previous week'}><Icon name="back"/></button><ol className="week-compass-days" aria-label={de?`Kalenderwoche ${week}`:`Week ${week}`}>{days.map(day=>{const rows=byDay.get(day.key)||[];const holiday=rows.find(isHolidayEvent);const markerRows=rows.filter(event=>!isHolidayEvent(event));const visible=markerRows.slice(0,compact?2:3);const hidden=Math.max(0,markerRows.length-visible.length);const parts=formatter.formatToParts(day.date);const weekday=parts.find(part=>part.type==='weekday')?.value?.replace('.','')||'';const number=parts.find(part=>part.type==='day')?.value||'';const description=rows.length?rows.map(event=>event.title).join(', '):(de?'Keine Ereignisse':'No events');return <li key={day.key} className={`${day.current?'current ':''}${holiday?'has-holiday':''}`}><button onClick={()=>window.location.assign(`/?page=calendar&day=${day.key}`)} aria-current={day.current?'date':undefined} aria-label={`${weekday} ${number}. ${description}`}><span className="week-day-name">{weekday}</span><strong>{number}</strong>{holiday&&<span className="week-holiday-mark" aria-hidden="true"><Icon name="school" size={9}/></span>}<span className="week-markers" aria-hidden="true">{visible.map((event,index)=>{const marker=eventMarker(event);return <i key={`${event.id}-${index}`} className={`week-marker ${marker.className}`}><Icon name={marker.icon} size={7}/></i>})}{hidden>0&&<em>+{hidden}</em>}</span></button></li>})}</ol><button className="week-compass-nav" onClick={()=>setWeekOffset(value=>value+1)} aria-label={de?'Nächste Woche':'Next week'}><Icon name="next"/></button></div>
 {failed&&<small className="week-widget-status">{de?'Kalenderdaten konnten gerade nicht geladen werden.':'Calendar data could not be loaded.'}</small>}</section>
}

const pinWidgetCopy={
 de:{kicker:'GEMEINSAM IM BLICK',title:'Pinnwand',open:'Öffnen',pin:'Anpinnen',loading:'Pinnwand wird geladen …',empty:'Ersten wichtigen Punkt anpinnen',hint:'Notiz, Foto, Termin, Aufgabe oder Einkaufsliste',error:'Die Pinnwand konnte nicht geladen werden.',stale:'Der letzte bestätigte Stand bleibt sichtbar.',denied:'Diese Pinnwand ist nicht mehr verfügbar.',retry:'Erneut laden',unavailable:'Nicht mehr verfügbar',author:'Angepinnt von'},
 en:{kicker:'SHARED AT A GLANCE',title:'Pinboard',open:'Open',pin:'Pin something',loading:'Loading pinboard …',empty:'Pin the first important item',hint:'Note, photo, event, task or shopping list',error:'Could not load the pinboard.',stale:'The last confirmed state remains visible.',denied:'This pinboard is no longer available.',retry:'Retry',unavailable:'No longer available',author:'Pinned by'},
 fr:{kicker:'EN UN COUP D’ŒIL',title:'Tableau familial',open:'Ouvrir',pin:'Épingler',loading:'Chargement du tableau…',empty:'Épinglez le premier élément important',hint:'Épinglez une note, une photo ou un élément existant',error:'Impossible de charger le tableau.',stale:'Le dernier état confirmé reste affiché.',denied:'Ce tableau n’est plus disponible.',retry:'Réessayer',unavailable:'Plus disponible',author:'Épinglé par'},
 nl:{kicker:'SAMEN IN BEELD',title:'Prikbord',open:'Openen',pin:'Vastmaken',loading:'Prikbord laden…',empty:'Maak het eerste belangrijke item vast',hint:'Maak een notitie, foto of bestaand item vast',error:'Prikbord laden mislukt.',stale:'De laatst bevestigde stand blijft zichtbaar.',denied:'Dit prikbord is niet meer beschikbaar.',retry:'Opnieuw proberen',unavailable:'Niet meer beschikbaar',author:'Vastgemaakt door'},
 th:{kicker:'มองภาพรวมร่วมกัน',title:'กระดานครอบครัว',open:'เปิด',pin:'ปักหมุด',loading:'กำลังโหลดกระดาน…',empty:'ปักหมุดรายการสำคัญรายการแรก',hint:'ปักหมุดบันทึก รูปภาพ หรือรายการที่มีอยู่',error:'โหลดกระดานไม่ได้',stale:'ยังคงแสดงสถานะที่ยืนยันล่าสุด',denied:'กระดานนี้ไม่พร้อมใช้งานแล้ว',retry:'ลองอีกครั้ง',unavailable:'ไม่พร้อมใช้งานแล้ว',author:'ปักหมุดโดย'}
};

const pinTypeCopy={
 de:{note:'Notizzettel',photo:'Foto',event:'Termin',task:'Aufgabe',routine:'Routine',note_ref:'Notiz',shopping:'Einkaufsartikel',shopping_list:'Einkaufsliste',trip:'Reise',document:'Dokument',holiday:'Ferien'},
 en:{note:'Note',photo:'Photo',event:'Event',task:'Task',routine:'Routine',note_ref:'Note',shopping:'Shopping item',shopping_list:'Shopping list',trip:'Trip',document:'Document',holiday:'School holidays'},
 fr:{note:'Note',photo:'Photo',event:'Rendez-vous',task:'Tâche',routine:'Routine',note_ref:'Note',shopping:'Article',shopping_list:'Liste de courses',trip:'Voyage',document:'Document',holiday:'Vacances scolaires'},
 nl:{note:'Notitie',photo:'Foto',event:'Afspraak',task:'Taak',routine:'Routine',note_ref:'Notitie',shopping:'Boodschap',shopping_list:'Boodschappenlijst',trip:'Reis',document:'Document',holiday:'Schoolvakantie'},
 th:{note:'บันทึก',photo:'รูปภาพ',event:'นัดหมาย',task:'งาน',routine:'กิจวัตร',note_ref:'บันทึก',shopping:'รายการซื้อของ',shopping_list:'รายการซื้อของ',trip:'การเดินทาง',document:'เอกสาร',holiday:'วันหยุดโรงเรียน'}
};

export function PinboardTodayWidget({family,language='de',compact=false}){
 const w=pinWidgetCopy[String(language).split('-')[0]]||pinWidgetCopy.en,de=language.startsWith('de');
 const [view,setView]=useState({familyId:null,pins:[],status:'loading',error:''});const lease=useRef(null);
 if(lease.current?.familyId!==family.id){if(lease.current)lease.current.active=false;lease.current={familyId:family.id,active:true,request:0,inFlight:null,queued:false}}
 const current=context=>context.active&&lease.current===context;
 async function load(){
  const context=lease.current;if(!current(context))return;if(context.inFlight){context.queued=true;return context.inFlight}
  const request=++context.request;
  setView(previous=>previous.familyId===context.familyId?{...previous,status:previous.pins.length?'ready':'loading',error:''}:{familyId:context.familyId,pins:[],status:'loading',error:''});
  const pending=(async()=>{try{const result=await api(`/board/?family=${encodeURIComponent(context.familyId)}`);if(!current(context)||request!==context.request)return;setView({familyId:context.familyId,pins:unwrap(result).filter(pin=>String(pin.family)===String(context.familyId)),status:'ready',error:''})}catch(error){if(!current(context)||request!==context.request)return;const denied=[401,403,404].includes(error.status)||error.message==='unauthorized';setView(previous=>({familyId:context.familyId,pins:denied?[]:previous.familyId===context.familyId?previous.pins:[],status:'ready',error:denied?'denied':'error'}))}finally{if(!current(context))return;context.inFlight=null;if(context.queued){context.queued=false;load()}}})();context.inFlight=pending;return pending;
 }
 useEffect(()=>{const context=lease.current;context.active=true;load();const focus=()=>{if(document.visibilityState!=='hidden')load()};const auth=event=>{if(event.detail?.authenticated===false){context.active=false;context.request+=1;setView({familyId:context.familyId,pins:[],status:'ready',error:'denied'})}};window.addEventListener('focus',focus);document.addEventListener('visibilitychange',focus);window.addEventListener(AUTH_CHANGED_EVENT,auth);return()=>{context.active=false;window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',focus);window.removeEventListener(AUTH_CHANGED_EVENT,auth)}},[family.id]);
 const state=view.familyId===family.id?view:{pins:[],status:'loading',error:''},pins=state.pins.slice(0,compact?2:4);
 function updateInteraction(id,interaction){const context=lease.current;if(!current(context))return;context.request+=1;context.queued=Boolean(context.inFlight);setView(previous=>previous.familyId!==context.familyId?previous:{...previous,pins:interaction?.can_interact===false?previous.pins.filter(pin=>pin.id!==id):previous.pins.map(pin=>pin.id===id?{...pin,interaction}:pin),status:'ready'});if(interaction?.can_interact===false)load()}
 const open=compose=>window.location.assign(`/?page=board&family=${encodeURIComponent(family.id)}${compose?'&compose=1':''}`);
 return <section className="today-section today-pinboard" data-testid="today-pinboard"><div className="today-section-head"><div><small>{w.kicker}</small><h2>{w.title}</h2></div><button type="button" className="today-link" onClick={()=>open(false)}>{w.open} <Icon name="next"/></button></div>
 {state.error&&<div className="today-calm" role="alert"><strong>{w[state.error]}</strong>{pins.length>0&&<span>{w.stale}</span>}<button type="button" className="secondary" onClick={load}>{w.retry}</button></div>}
 {pins.length?<div className="today-pinboard-grid today-pinboard-interactive">{pins.map(pin=><article key={pin.id} className="today-pin-card" data-today-pin={pin.id}><PinPreview pin={pin} de={de} language={language} w={w}/>{pin.can_interact&&pin.target?.available!==false&&<PinInteractionBar pin={pin} compact onChange={interaction=>updateInteraction(pin.id,interaction)}/>}</article>)}</div>:state.error?null:state.status==='loading'?<div className="today-calm" role="status">{w.loading}</div>:<button type="button" className="today-pinboard-empty" onClick={()=>open(true)}><span><Icon name="plus"/></span><strong>{w.empty}</strong><small>{w.hint}</small></button>}
 <div className="today-pinboard-actions"><button type="button" className="secondary compact" onClick={()=>open(true)}><Icon name="plus"/> {w.pin}</button></div></section>
}

function PinPreview({pin,de,language,w}){
 const target=pin.target,unavailable=target?.available===false,event=target?.event_type?{type:target.event_type,starts_at:target.subtitle,ends_at:target.ends_at,payload:{date_start:target.date_start,date_end_exclusive:target.date_end_exclusive}}:null;
 const href=unavailable?`/?page=board&family=${encodeURIComponent(pin.family)}&post=${encodeURIComponent(pin.id)}`:target?.url||`/?page=board&family=${encodeURIComponent(pin.family)}&post=${encodeURIComponent(pin.id)}`;
 const holiday=pin.kind==='event'&&isHolidayEvent(event),type=(pinTypeCopy[String(language).split('-')[0]]||pinTypeCopy.en)[holiday?'holiday':pin.kind]||pinTypeLabel(pin.kind,de,event),title=unavailable?w.unavailable:target?.title||pin.text||type,meta=unavailable?'':pin.kind==='event'?formatPinEventMeta(event,language):target?.subtitle||'',authorStyle={'--pin-author-hue':pinAuthorHue(pin.author)};
 return <button type="button" className={`today-pin ${pin.kind||'note'} ${holiday?'event-holiday ':''}${unavailable?'unavailable':''}`} onClick={()=>window.location.assign(href)} aria-label={`${type}: ${title}. ${w.author} ${pin.author_name||''}`}>
  {!unavailable&&pin.images?.[0]&&<img src={pin.images[0].url} alt="" width={pin.images[0].width} height={pin.images[0].height} loading="lazy"/>}
  <span className="today-pin-type" aria-hidden="true"><Icon name={pinIconName(pin.kind,event)}/></span>
  <span className="today-pin-copy"><span className="today-pin-kicker"><span className="today-pin-kind">{type}</span><span className="today-pin-author" style={authorStyle} title={`${w.author} ${pin.author_name||''}`}><span className="today-pin-author-avatar" aria-hidden="true">{pinAuthorInitial(pin.author_name)}</span><span className="today-pin-author-name">{pin.author_name}</span></span></span><strong>{String(title).slice(0,100)}</strong>{meta&&<small>{formatMeta(meta,language)}</small>}</span>
 </button>
}

function formatMeta(value,language){if(!value)return'';if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}T/.test(value)){const date=new Date(value);if(!Number.isNaN(date.getTime()))return date.toLocaleString(language,{dateStyle:'short',timeStyle:'short'})}return String(value).slice(0,120)}
