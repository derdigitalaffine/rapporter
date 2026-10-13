import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import i18n from './i18n';
import './calendar-i18n';
import './birthday-i18n';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import {formatDateTime} from './locale';
import {isWasteEvent,wasteClass,wasteKind,wasteKindLabel} from './waste-ui';
import {eventSourceDescriptor,eventSourceFilterKey,eventSourceStyle,isHolidayEvent,isNativeCalendarEvent} from './calendar-event-ui';
import {eventMemberDescriptors} from './calendar-members';
import {fetchCalendarEvents} from './calendar-events-api';
import CalendarPresentation,{calendarViewFromLocation} from './CalendarPresentation';
import CalendarParticipantAvatars from './CalendarParticipantAvatars';
import EventEditor from './EventEditor';
import './calendar-hub.css';
import './calendar-health.css';
import './calendar-participants.css';

const CALENDAR_SOURCE_FILTERS=new Set(['birthday','family','warning','waste','weather','transit','school','calendar']);
const CALENDAR_LIST_DENSITY_KEY='familyos:calendar:list-density:v1';

export default function CalendarHub({family,onBack,t}){
 const [events,setEvents]=useState([]);const [integrations,setIntegrations]=useState([]);const [calendarMembers,setCalendarMembers]=useState([]);const [currentMembershipId,setCurrentMembershipId]=useState('');const [edit,setEdit]=useState(null);const [detail,setDetail]=useState(null);const [filter,setFilter]=useState(calendarSourceFilterFromLocation);const [showPast,setShowPast]=useState(false);const [view,setView]=useState(calendarViewFromLocation);
 const [selectionMode,setSelectionMode]=useState(false);const [selectedIds,setSelectedIds]=useState(()=>new Set());const [listDensity,setListDensity]=useState(readCalendarListDensity);const [batchBusy,setBatchBusy]=useState(false);
 const loadSequence=useRef(0);const lastRange=useRef(null);const previousFamilyId=useRef(family?.id);
 const targetDay=new URLSearchParams(window.location.search).get('day');
 const calendarFamily=useMemo(()=>({...family,memberships:calendarMembers.length?calendarMembers:(family?.memberships||[]),current_membership_id:currentMembershipId||null}),[family,calendarMembers,currentMembershipId]);
 const load=useCallback(async(range={})=>{
  lastRange.current=range;const sequence=++loadSequence.current;
  try{
   const rows=await fetchCalendarEvents({familyId:family?.id,...range});
   if(sequence!==loadSequence.current)return;
   setEvents(rows.filter(x=>!family||String(x.family)===String(family.id)).sort((a,b)=>eventTime(a)-eventTime(b)));
  }catch(e){if(sequence===loadSequence.current){setEvents([]);toast(e.message||t('saveFailed'),{type:'error'})}}
 },[family?.id,t]);
 useEffect(()=>{
  let live=true;
  setIntegrations([]);setCalendarMembers([]);setCurrentMembershipId('');
  if(!family?.id)return()=>{live=false};
  api('/integrations/').then(value=>{
   if(!live)return;
   const rows=value?.results||value||[];
   setIntegrations(rows.filter(row=>String(row.family)===String(family.id)));
  }).catch(()=>{if(live)setIntegrations([])});
  api('/memberships/').then(value=>{
   if(!live)return;
   const rows=value?.results||value||[];
   setCalendarMembers(rows.filter(row=>String(row.family)===String(family.id)));
  }).catch(()=>{if(live)setCalendarMembers([])});
  api(`/profile/?family=${encodeURIComponent(family.id)}`).then(value=>{if(live)setCurrentMembershipId(value?.membership_id||'')}).catch(()=>{if(live)setCurrentMembershipId('')});
  return()=>{live=false};
 },[family?.id]);
 useEffect(()=>{
  const familyChanged=previousFamilyId.current!=null&&family?.id!=null&&String(previousFamilyId.current)!==String(family.id);
  previousFamilyId.current=family?.id;
  setEvents([]);setSelectionMode(false);setSelectedIds(new Set());
  if(familyChanged){setFilter('all');replaceCalendarQuery('source',null)}else setFilter(calendarSourceFilterFromLocation());
  setShowPast(Boolean(targetDay&&targetDay<dayKey(new Date())));
 },[family?.id,targetDay]);
 const filters=useMemo(()=>{const map=new Map();events.forEach(event=>{const source=eventSourceDescriptor(event,t);if(!map.has(source.filterKey))map.set(source.filterKey,source)});return [...map.values()]},[events,t]);
 const unhealthySources=useMemo(()=>{
  const activeSourceIds=new Set(events.map(event=>event?.source_meta?.id).filter(Boolean).map(String));
  return integrations.filter(source=>source.enabled&&source.last_sync_status==='error'&&activeSourceIds.has(String(source.id)));
 },[events,integrations]);
 const sourceFiltered=useMemo(()=>filter==='all'?events:events.filter(e=>eventSourceFilterKey(e)===filter),[events,filter]);
 const hasPast=useMemo(()=>sourceFiltered.some(eventIsPast),[sourceFiltered]);
 const visible=useMemo(()=>showPast?sourceFiltered:sourceFiltered.filter(e=>!eventIsPast(e)),[sourceFiltered,showPast]);
 const grouped=useMemo(()=>groupByDay(visible),[visible]);
 const selectableVisible=useMemo(()=>visible.filter(isNativeCalendarEvent),[visible]);
 const selectableIds=useMemo(()=>new Set(selectableVisible.map(event=>String(event.id))),[selectableVisible]);
 const allSelectableSelected=selectableVisible.length>0&&selectableVisible.every(event=>selectedIds.has(String(event.id)));
 useEffect(()=>{if(view!=='list'){setSelectionMode(false);setSelectedIds(new Set())}},[view]);
 useEffect(()=>{setSelectedIds(current=>{const next=new Set([...current].filter(id=>selectableIds.has(id)));if(next.size===current.size&&[...next].every(id=>current.has(id)))return current;return next})},[selectableIds]);
 useEffect(()=>{if(view!=='list'||!targetDay)return;const timer=setTimeout(()=>document.getElementById(`calendar-day-${targetDay}`)?.scrollIntoView({block:'start',behavior:'smooth'}),60);return()=>clearTimeout(timer)},[targetDay,grouped.length,showPast,view]);
 function editEvent(e){setDetail(null);setEdit(e)}
 function openEvent(e){if(e.type==='birthday'&&e.payload?.url){window.location.assign(e.payload.url);return}setDetail(e)}
 function changeFilter(next){
  const value=next==='all'||isCalendarSourceFilter(next)?next:'all';
  setFilter(value);
  replaceCalendarQuery('source',value==='all'?null:value);
 }
 function changeView(next){
  if(!['week','month','list'].includes(next))return;
  setView(next);
  replaceCalendarQuery('view',next==='week'?null:next);
 }
 function changeListDensity(next){
  const value=next==='compact'?'compact':'normal';
  setListDensity(value);writeCalendarListDensity(value);
 }
 function startSelection(){setDetail(null);setSelectionMode(true)}
 function stopSelection(){if(batchBusy)return;setSelectionMode(false);setSelectedIds(new Set())}
 function toggleSelection(event){
  if(batchBusy||!isNativeCalendarEvent(event))return;
  const id=String(event.id);
  setSelectedIds(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next});
 }
 function toggleAllSelectable(){
  if(batchBusy)return;
  setSelectedIds(allSelectableSelected?new Set():new Set(selectableVisible.map(event=>String(event.id))));
 }
 async function deleteSelected(){
  const ids=[...selectedIds].filter(id=>selectableIds.has(id));
  if(!ids.length||batchBusy)return;
  const confirmed=await confirmAction({title:t('calendarUi.deleteSelectedTitle'),message:t('calendarUi.deleteSelectedMessage',{count:ids.length}),confirmLabel:t('calendarUi.deleteSelected'),cancelLabel:t('cancel'),danger:true});
  if(!confirmed)return;
  setBatchBusy(true);
  const requested=new Set(ids);
  try{
   const failed=await deleteCalendarEvents(ids);
   const failedSet=new Set(failed);
   const deleted=ids.length-failed.length;
   if(deleted)setEvents(rows=>rows.filter(row=>!requested.has(String(row.id))||failedSet.has(String(row.id))));
   setSelectedIds(failedSet);
   if(failed.length)toast(t('calendarUi.deleteSelectedPartial',{deleted,failed:failed.length}),{type:'error'});
   else{setSelectionMode(false);toast(t('calendarUi.deleteSelectedSuccess',{count:deleted}),{type:'success'})}
   if(lastRange.current)await load(lastRange.current);
  }finally{setBatchBusy(false)}
 }
 async function eventSaved(saved,{deleted=false}={}){
  const editedId=edit?.id;
  setEdit(null);
  if(saved){setEvents(rows=>[...rows.filter(row=>String(row.id)!==String(saved.id)),saved].filter(row=>!family||String(row.family)===String(family.id)).sort((a,b)=>eventTime(a)-eventTime(b)))}
  else if(deleted&&editedId){setEvents(rows=>rows.filter(row=>String(row.id)!==String(editedId)))}
  if(lastRange.current)await load(lastRange.current);
 }
 const language=i18n.language;
 const listContent=<><div className="calendar-list-toolbar" role="toolbar" aria-label={t('calendarUi.listTools')}>
  <div className="calendar-list-density" role="group" aria-label={t('calendarUi.listDensity')}><span>{t('calendarUi.listDensity')}</span><button type="button" className="secondary compact" aria-pressed={listDensity==='normal'} onClick={()=>changeListDensity('normal')}>{t('calendarUi.densityNormal')}</button><button type="button" className="secondary compact" aria-pressed={listDensity==='compact'} onClick={()=>changeListDensity('compact')}>{t('calendarUi.densityCompact')}</button></div>
  <div className="calendar-list-actions">{selectionMode?<><span className="calendar-selection-count" aria-live="polite">{t('calendarUi.selectedCount',{count:selectedIds.size})}</span><button type="button" className="secondary compact" onClick={toggleAllSelectable} disabled={batchBusy||selectableVisible.length===0}>{t(allSelectableSelected?'calendarUi.clearSelection':'calendarUi.selectAllVisible')}</button><button type="button" className="secondary compact" onClick={stopSelection} disabled={batchBusy}>{t('calendarUi.selectionDone')}</button><button type="button" className="calendar-bulk-delete" onClick={deleteSelected} disabled={batchBusy||selectedIds.size===0}><Icon name="delete"/>{t('calendarUi.deleteSelected')}</button></>:<button type="button" className="secondary compact" onClick={startSelection} disabled={selectableVisible.length===0}><Icon name="check"/>{t('calendarUi.selectEvents')}</button>}</div>
 </div>{hasPast&&<div className="calendar-history-toggle"><button className="secondary compact" aria-pressed={showPast} onClick={()=>setShowPast(value=>!value)}><Icon name="calendar"/>{t(showPast?'calendarUi.hidePast':'calendarUi.showPast')}</button></div>}
 <div className={`agenda-days ${listDensity==='compact'?'calendar-list-compact':''} ${selectionMode?'calendar-selection-mode':''}`}>{grouped.length?grouped.map(([day,rows])=><section className={`agenda-day ${targetDay===day?'agenda-day-target':''}`} id={`calendar-day-${day}`} key={day}><div className="agenda-day-head"><div><small>{dayRelativeLabel(day,t,language)}</small><h2>{dayLongLabel(day,t,language)}</h2></div><span>{rows.length}</span></div><div className="agenda-list">{rows.map(e=><CalendarListRow key={e.id} event={e} family={calendarFamily} t={t} language={language} selecting={selectionMode} selected={selectedIds.has(String(e.id))} disabled={batchBusy} onToggle={()=>toggleSelection(e)} onOpen={()=>openEvent(e)}/>)}</div></section>):<div className="smart-empty"><Icon name="calendar" size={34}/><strong>{t('noUpcoming')}</strong><span>{filter==='all'?t('calendarAddHint'):t('calendarUi.noSourceEntries')}</span>{filter!=='all'&&<button className="secondary compact" onClick={()=>changeFilter('all')}>{t('calendarUi.showAllSources')}</button>}</div>}</div></>;
 return <div className="smart-page calendar-agenda"><div className="page-head"><button className="back-button" onClick={onBack} aria-label={t('back')}><Icon name="back"/></button><div className="grow"><small>{t('calendarUi.familyCalendar')}</small><h1>{t('calendar')}</h1></div></div><p className="page-intro">{t('calendarUi.calendarIntro')}</p>
 {unhealthySources.length>0&&<CalendarSourceHealth sources={unhealthySources} t={t}/>} 
 {(filters.length>1||filter!=='all')&&<div className="calendar-filters" aria-label={t('calendarUi.sources')}><button className={filter==='all'?'active':''} onClick={()=>changeFilter('all')}><Icon name="calendar"/> {t('all')}</button>{filters.map(source=><button key={source.filterKey} className={filter===source.filterKey?'active':''} onClick={()=>changeFilter(source.filterKey)}><Icon name={source.icon}/>{source.key==='family'?(family?.name||source.label):source.label}</button>)}</div>}
 <CalendarPresentation view={view} onViewChange={changeView} onRangeChange={load} events={sourceFiltered} family={calendarFamily} t={t} language={language} onOpen={openEvent} targetDay={targetDay} listContent={listContent}/>
 {detail&&<EventDetail event={detail} family={calendarFamily} t={t} language={language} onClose={()=>setDetail(null)} onEdit={isNativeCalendarEvent(detail)?()=>editEvent(detail):null}/>} 
 {edit&&<EventEditor family={calendarFamily} event={edit.id?edit:null} onClose={()=>setEdit(null)} onSaved={eventSaved}/>}</div>
}

function CalendarSourceHealth({sources,t}){const names=sources.map(source=>source.name).filter(Boolean).join(' · ');return <aside className="calendar-source-health" role="status" aria-live="polite"><span className="calendar-source-health-icon" aria-hidden="true"><Icon name="warning"/></span><div className="calendar-source-health-copy"><strong>{sources.length===1?t('calendarUi.sourceHealthOne'):t('calendarUi.sourceHealthMany',{count:sources.length})}</strong><span>{names}</span></div><a className="calendar-source-health-link" href="/?page=integrations"><span>{t('calendarUi.sourceHealthOpen')}</span><Icon name="next"/></a></aside>}

function CalendarListRow({event,family,t,language,selecting,selected,disabled,onToggle,onOpen}){const selectable=isNativeCalendarEvent(event);if(!selecting)return <CalendarEventRow event={event} family={family} t={t} language={language} onOpen={onOpen}/>;return <div className={`calendar-selection-row ${selectable?'is-selectable':'is-readonly'} ${selected?'is-selected':''}`}>{selectable?<label className="calendar-row-check"><input type="checkbox" checked={selected} disabled={disabled} onChange={onToggle} aria-label={t('calendarUi.selectEvent',{title:event.title})}/></label>:<span className="calendar-row-check calendar-row-check-disabled" role="img" aria-label={t('calendarUi.readonlySelection')}><Icon name="info"/></span>}<div className="calendar-selection-event"><CalendarEventRow event={event} family={family} t={t} language={language} onOpen={selectable?onToggle:onOpen} selecting={selecting} selected={selected}/></div></div>}

function CalendarEventRow(props){if(isHolidayEvent(props.event))return <HolidayEvent {...props}/>;if(isWasteEvent(props.event))return <WasteEvent {...props}/>;return <AgendaEvent {...props}/>}

function HolidayEvent({event,t,language,onOpen}){const de=language.startsWith('de');const source=eventSourceDescriptor(event,t);const sourceName=event.source_meta?source.label:(de?'Schulferien':'School holidays');return <button className="agenda-special agenda-holiday" onClick={onOpen}><span className="special-rail" aria-hidden="true"/><span className="agenda-special-icon"><Icon name={source.icon}/></span><div className="grow"><div className="agenda-special-label">{de?'FERIEN':'SCHOOL HOLIDAY'}</div><strong>{event.title}</strong><span>{formatHolidayRange(event,t,language)}</span></div><span className="agenda-special-source"><Icon name={source.icon}/>{sourceName}</span><Icon name="next" className="agenda-affordance"/></button>}

function WasteEvent({event,t,language,onOpen}){const kind=wasteKind(event);const tone=wasteClass(event);const de=language.startsWith('de');const source=eventSourceDescriptor(event,t);return <button className={`agenda-special agenda-waste ${tone}`} onClick={onOpen}><span className={`waste-dot ${tone}`} aria-hidden="true"><Icon name="waste" size={8}/></span><span className="agenda-special-icon"><Icon name={source.icon}/></span><div className="grow"><div className="agenda-special-label">{de?'MÜLLABFUHR':'WASTE COLLECTION'}</div><strong>{event.title}</strong><span>{wasteKindLabel(kind,language)}{event.payload?.location?` · ${event.payload.location}`:''}</span></div><span className={`agenda-special-source ${tone}`}><Icon name={source.icon}/>{source.label}</span><Icon name="next" className="agenda-affordance"/></button>}

function AgendaEvent({event,family,t,language,onOpen,selecting=false,selected=false}){const source=eventSourceDescriptor(event,t);const native=isNativeCalendarEvent(event);const warning=source.key==='warning';const label=source.key==='family'?(family?.name||source.label):source.label;const style=sourceVisualStyle(event);return <button className={`agenda-event ${warning?'agenda-warning':''}`} onClick={onOpen} aria-pressed={selecting&&native?selected:undefined}><div className="agenda-time">{event.payload?.all_day?<strong>{t('calendarUi.allDay')}</strong>:<><strong>{formatTime(event.starts_at,language)}</strong>{event.ends_at&&<span>{formatEndTime(event,language)}</span>}</>}</div><span className={`agenda-source-icon source-${source.key}`} style={style}><Icon name={source.icon}/></span><div className="grow agenda-event-main"><div className="agenda-title-line"><strong>{event.title}</strong>{event.payload?.delay_minutes>0&&<span className="delay-badge">+{event.payload.delay_minutes} min</span>}</div><div className="agenda-event-meta">{event.payload?.location&&<span><Icon name="location"/>{event.payload.location}</span>}<span className={`source-badge source-${source.key}`} style={style}><Icon name={source.icon}/>{label}</span><CalendarParticipantAvatars event={event} family={family} max={3} size={22} withNames/>{event.is_family_event&&<span className="calendar-family-event-badge"><Icon name="members" size={12}/>{t('calendarUi.familyEvent')}</span>}{event.payload?.recurrence&&<span><Icon name="refresh"/> {recurrenceLabel(event.payload.recurrence,t)}</span>}</div></div><Icon name={native?'edit':'next'} className="agenda-affordance"/></button>}

function EventDetail({event,family,t,language,onClose,onEdit}){const source=eventSourceDescriptor(event,t);const members=eventMemberDescriptors(event,family);const displayLabel=isHolidayEvent(event)&&!event.source_meta?(language.startsWith('de')?'Ferien':'School holiday'):source.key==='family'?(family?.name||source.label):source.label;const provider=isNativeCalendarEvent(event)?'FamilyOS':displayLabel;const wasteTone=source.key==='waste'?wasteClass(event):'';const special=isHolidayEvent(event)?'holiday-detail':isWasteEvent(event)?'waste-detail':'';const style=sourceVisualStyle(event);return <div className="sheet-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section className={`quick-sheet calendar-detail ${source.key==='warning'?'warning-detail':''} ${special}`} role="dialog" aria-modal="true"><div className="sheet-handle"/><div className="sheet-head"><div><span className={`source-badge source-${source.key} ${wasteTone}`} style={style}><Icon name={source.icon}/>{displayLabel}</span><h2>{event.title}</h2></div><button className="sheet-close" onClick={onClose} aria-label={t('back')}><Icon name="close"/></button></div><div className="event-detail-body"><div className="event-detail-primary"><span className={`agenda-source-icon source-${source.key} ${wasteTone}`} style={style}><Icon name={source.icon}/></span><div><strong>{formatFullDate(event,t,language)}</strong><span>{formatEventRange(event,t,language)}</span></div></div>{event.payload?.location&&<DetailRow icon="location" label={t('location')} value={event.payload.location}/>} {event.payload?.description&&<DetailRow icon="info" label={t('notes')} value={event.payload.description}/>} {members.length>0&&<div className="event-detail-row"><Icon name="user"/><div><small>{t(members.length===1?'calendarUi.person':'calendarUi.participants')}</small><CalendarParticipantAvatars event={event} family={family} max={6} size={30} withNames/></div></div>} {event.is_family_event&&<DetailRow icon="members" label={t('calendarUi.eventKind')} value={t('calendarUi.familyEvent')}/>} {event.payload?.recurrence&&<DetailRow icon="refresh" label={t('recurrence')} value={recurrenceLabel(event.payload.recurrence,t)}/>} {event.payload?.delay_minutes>0&&<DetailRow icon="transit" label={t('calendarUi.delay')} value={`+${event.payload.delay_minutes} ${t('calendarUi.minutes')}`}/>}<DetailRow icon="integrations" label={t('calendarUi.source')} value={provider}/>{event.payload?.source_url==='https://bm.rlp.de/service/ferientermine'&&<a className="text-link" href={event.payload.source_url} target="_blank" rel="noreferrer"><Icon name="link"/>{t('calendarUi.officialSource')}</a>}</div>{onEdit?<button className="primary" onClick={onEdit}><Icon name="edit"/>{t('editEvent')}</button>:<div className="readonly-event-note"><Icon name="info"/><span>{t('calendarUi.readonly')}</span></div>}</section></div>}
function DetailRow({icon,label,value}){return <div className="event-detail-row"><Icon name={icon}/><div><small>{label}</small><span>{value}</span></div></div>}

function isCalendarSourceFilter(value){return CALENDAR_SOURCE_FILTERS.has(value)||/^integration:[A-Za-z0-9_-]{1,80}$/.test(value||'')}
function calendarSourceFilterFromLocation(){const value=new URLSearchParams(window.location.search).get('source');return isCalendarSourceFilter(value)?value:'all'}
function replaceCalendarQuery(name,value){const url=new URL(window.location.href);if(value==null)url.searchParams.delete(name);else url.searchParams.set(name,value);window.history.replaceState(window.history.state,'',`${url.pathname}${url.search}${url.hash}`)}
function readCalendarListDensity(){try{return window.localStorage.getItem(CALENDAR_LIST_DENSITY_KEY)==='compact'?'compact':'normal'}catch{return'normal'}}
function writeCalendarListDensity(value){try{window.localStorage.setItem(CALENDAR_LIST_DENSITY_KEY,value)}catch{}}
async function deleteCalendarEvents(ids){const failed=[];for(let index=0;index<ids.length;index+=6){const chunk=ids.slice(index,index+6);const results=await Promise.allSettled(chunk.map(id=>api(`/events/${encodeURIComponent(id)}/`,{method:'DELETE'})));results.forEach((result,offset)=>{if(result.status==='rejected')failed.push(chunk[offset])})}return failed}
function sourceVisualStyle(event){const vars=eventSourceStyle(event);return {...vars,background:vars['--event-soft'],color:vars['--event-tone']}}
function eventTime(event){return event.starts_at?new Date(event.starts_at).getTime():Number.MAX_SAFE_INTEGER}
function eventIsPast(event){if(!event.starts_at)return false;const boundary=event.ends_at||event.starts_at;return new Date(boundary).getTime()<Date.now()}
function dayKey(value){if(!value)return'undated';const d=value instanceof Date?value:new Date(value);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function groupByDay(events){const groups=new Map();events.forEach(event=>{const key=event.payload?.date_start||dayKey(event.starts_at);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(event)});return [...groups.entries()]}
function localDay(key){if(key==='undated')return null;const [y,m,d]=key.split('-').map(Number);return new Date(y,m-1,d)}
function dayRelativeLabel(key,t,language){const date=localDay(key);if(!date)return t('calendarUi.undatedUpper');const today=new Date();today.setHours(0,0,0,0);const target=new Date(date);target.setHours(0,0,0,0);const diff=Math.round((target-today)/86400000);if(diff===0)return t('calendarUi.todayUpper');if(diff===1)return t('calendarUi.tomorrowUpper');if(diff===-1)return t('calendarUi.yesterdayUpper');return formatDateTime(language,date,{weekday:'long'}).toUpperCase()}
function dayLongLabel(key,t,language){const date=localDay(key);return date?formatDateTime(language,date,{day:'numeric',month:'long'}):t('calendarUi.undated')}
function formatTime(value,language){return value?formatDateTime(language,value,{hour:'2-digit',minute:'2-digit'}):'–'}
function formatEndTime(event,language){if(!event.ends_at)return'';const start=event.starts_at?new Date(event.starts_at):null,end=new Date(event.ends_at);if(start&&start.toDateString()!==end.toDateString())return formatDateTime(language,end,{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});return `– ${formatTime(event.ends_at,language)}`}
function formatFullDate(event,t,language){if(!event.starts_at&&!event.payload?.date_start)return t('calendarUi.noDate');return formatDateTime(language,event.payload?.date_start?localDay(event.payload.date_start):event.starts_at,{weekday:'long',day:'numeric',month:'long',year:'numeric'})}
function formatHolidayRange(event,t,language){const start=event.payload?.date_start,end=event.payload?.date_end_exclusive;if(!start)return formatFullDate(event,t,language);if(!end)return formatDateTime(language,localDay(start),{day:'numeric',month:'long'});const last=localDay(end);last.setDate(last.getDate()-1);return dayKey(last)===start?formatDateTime(language,localDay(start),{day:'numeric',month:'long'}):`${formatDateTime(language,localDay(start),{day:'numeric',month:'long'})} – ${formatDateTime(language,last,{day:'numeric',month:'long'})}`}
function formatEventRange(event,t,language){if(event.payload?.all_day){const start=event.payload.date_start,end=event.payload.date_end_exclusive;if(start&&end){const last=localDay(end);last.setDate(last.getDate()-1);if(dayKey(last)!==start)return `${formatDateTime(language,localDay(start),{day:'numeric',month:'long'})} – ${formatDateTime(language,last,{day:'numeric',month:'long',year:'numeric'})} · ${t('calendarUi.allDay')}`}return t('calendarUi.allDay')}if(!event.starts_at)return'';return `${formatTime(event.starts_at,language)}${event.ends_at?` ${formatEndTime(event,language)}`:''}`}
function recurrenceLabel(value,t){return value==='weekly'?t('weekly'):value==='monthly'?t('monthly'):value==='yearly'?t('yearly'):value}
