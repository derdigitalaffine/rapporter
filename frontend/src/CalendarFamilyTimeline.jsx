import {useEffect,useMemo,useRef,useState} from 'react';
import {Icon} from './icons';
import {formatDateTime} from './locale';
import MemberAvatar from './MemberAvatar';
import {eventDayKeys,eventSourceStyle} from './calendar-event-ui';
import {eventMemberDescriptors,membershipCalendarColor,membershipDisplayName} from './calendar-members';
import './calendar-family-timeline.css';

const FAMILY_LANE='__family__';
const ICS_LANE='__ics__';
const SETTINGS_KEY='familyos:calendar:timeline:v2';
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));

export default function CalendarFamilyTimeline({days,events,family,t,language,onOpen,today}){
 const timeZone=family?.timezone||'Europe/Berlin';
 const settings=useMemo(readTimelineSettings,[]);
 const [orientation,setOrientation]=useState(settings.orientation==='columns'?'columns':'rows');
 const [zoom,setZoom]=useState(clamp(Number(settings.zoom)||48,0,100));
 const [hiddenLaneIds,setHiddenLaneIds]=useState(()=>new Set(Array.isArray(settings.hiddenLaneIds)?settings.hiddenLaneIds.map(String):[]));
 const [viewport,setViewport]=useState({width:0,height:0});
 const scrollRef=useRef(null);
 const lanes=useMemo(()=>buildLanes(days,events,family,timeZone,t),[days,events,family,timeZone,t]);
 const visibleLanes=useMemo(()=>lanes.filter(lane=>!hiddenLaneIds.has(lane.id)),[lanes,hiddenLaneIds]);
 const daySize=58+(zoom*1.22);
 const rowSize=46+(zoom*.68);
 const visibleDays=useMemo(()=>estimateVisibleDays({orientation,viewport,daySize,rowSize,total:days.length}),[orientation,viewport,daySize,rowSize,days.length]);
 const peopleCount=visibleLanes.filter(lane=>lane.kind==='member').length;
 useEffect(()=>{writeTimelineSettings({orientation,zoom,hiddenLaneIds:[...hiddenLaneIds]})},[orientation,zoom,hiddenLaneIds]);
 useEffect(()=>{
  const node=scrollRef.current;if(!node)return;
  const update=()=>setViewport({width:node.clientWidth,height:node.clientHeight});update();
  if(typeof ResizeObserver==='undefined')return;
  const observer=new ResizeObserver(update);observer.observe(node);return()=>observer.disconnect();
 },[orientation]);
 function toggleLane(id){setHiddenLaneIds(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next})}
 function showAll(){setHiddenLaneIds(new Set())}
 return <section className={`calendar-view family-timeline orientation-${orientation}`} aria-label={t('calendarUi.viewTimeline')}>
  <div className="family-timeline-intro"><div><strong>{t('calendarUi.timelineTitle')}</strong><span>{t('calendarUi.timelineHint')}</span></div><span className="family-timeline-week-badge"><Icon name="members"/>{t('calendarUi.timelinePeople',{count:peopleCount})}</span></div>
  <div className="family-timeline-controls" role="toolbar" aria-label={t('calendarUi.timelineControls')}>
   <div className="family-timeline-orientation" role="group" aria-label={t('calendarUi.timelineOrientation')}>
    <button type="button" aria-pressed={orientation==='rows'} className={orientation==='rows'?'active':''} onClick={()=>setOrientation('rows')}><Icon name="members"/>{t('calendarUi.timelineOrientationRows')}</button>
    <button type="button" aria-pressed={orientation==='columns'} className={orientation==='columns'?'active':''} onClick={()=>setOrientation('columns')}><Icon name="refresh"/>{t('calendarUi.timelineOrientationColumns')}</button>
   </div>
   <label className="family-timeline-zoom"><span><Icon name="search"/>{t('calendarUi.timelineZoom')}</span><input type="range" min="0" max="100" step="1" value={zoom} onChange={event=>setZoom(Number(event.target.value))}/><output>{t('calendarUi.timelineVisibleDays',{count:visibleDays})}</output></label>
   <details className="family-timeline-lane-picker"><summary><Icon name="members"/><span>{t('calendarUi.timelineLanes')}</span><strong>{visibleLanes.length}/{lanes.length}</strong></summary><div className="family-timeline-lane-controls">
    <div className="family-timeline-lane-controls-head"><span>{t('calendarUi.timelineLanesHint')}</span>{hiddenLaneIds.size>0&&<button type="button" className="text-link" onClick={showAll}>{t('calendarUi.timelineShowAll')}</button>}</div>
    {lanes.map(lane=><label key={lane.id} className="family-timeline-lane-toggle">{lane.kind==='member'?<MemberAvatar person={lane.member} color={lane.color} size={28}/>:<span className={`family-timeline-control-icon is-${lane.kind}`}><Icon name={lane.kind==='ics'?'calendar':'members'}/></span>}<span className="grow"><strong>{lane.name}</strong><small>{lane.subtitle}</small></span><input type="checkbox" checked={!hiddenLaneIds.has(lane.id)} onChange={()=>toggleLane(lane.id)} aria-label={lane.name}/></label>)}
   </div></details>
  </div>
  {visibleLanes.length?<div ref={scrollRef} className="family-timeline-scroll" tabIndex="0" aria-label={t(orientation==='rows'?'calendarUi.timelineScrollHint':'calendarUi.timelineScrollHintVertical')}>
   {orientation==='rows'?<TimelineRows lanes={visibleLanes} days={days} family={family} t={t} language={language} onOpen={onOpen} today={today} daySize={daySize}/>:<TimelineColumns lanes={visibleLanes} days={days} family={family} t={t} language={language} onOpen={onOpen} today={today} rowSize={rowSize}/>} 
  </div>:<div className="family-timeline-empty"><Icon name="members"/><strong>{t('calendarUi.timelineNoLanes')}</strong><button type="button" className="secondary compact" onClick={showAll}>{t('calendarUi.timelineShowAll')}</button></div>}
 </section>;
}

function TimelineRows({lanes,days,family,t,language,onOpen,today,daySize}){
 return <div className="family-timeline-table family-timeline-rows" style={{'--timeline-day-width':`${daySize}px`,'--timeline-day-count':days.length}}>
  <div className="family-timeline-header family-timeline-row">
   <div className="family-timeline-label family-timeline-corner"><span>{t('calendarUi.timelinePeopleLabel')}</span></div>
   <div className="family-timeline-days">{days.map(day=><DayHead key={day} day={day} today={today} language={language}/>)}</div>
  </div>
  {lanes.map(lane=><TimelineLane key={lane.id} lane={lane} days={days} family={family} t={t} language={language} onOpen={onOpen}/>) }
 </div>;
}

function TimelineLane({lane,days,family,t,language,onOpen}){
 const packed=packEvents(lane.events,days,family?.timezone||'Europe/Berlin');
 const rows=Math.max(1,...packed.map(item=>item.level+1));
 const minHeight=Math.max(72,rows*46+20);
 return <div data-lane-id={lane.id} className={`family-timeline-row family-timeline-lane is-${lane.kind}`} style={{'--lane-color':lane.color||'var(--brand)','--timeline-lane-height':`${minHeight}px`}}>
  <LaneLabel lane={lane}/>
  <div className="family-timeline-track" style={{'--timeline-rows':rows}}>
   {days.map(day=><span key={day} className="family-timeline-grid-cell" aria-hidden="true"/>)}
   {packed.length?packed.map(item=><button key={`${lane.id}-${item.event.id}-${item.start}`} className="family-timeline-event" style={{gridColumn:`${item.start+1} / ${item.end+2}`,gridRow:item.level+1,...timelineEventStyle(item.event,lane)}} onClick={()=>onOpen(item.event)} title={timelineTitle(item.event,language,t)}>
    <span className="family-timeline-event-time">{eventTimeLabel(item.event,language,t,item.span)}</span>
    <strong>{item.event.title}</strong>
    {(item.event.payload?.location||lane.kind==='ics')&&<small><Icon name={item.event.payload?.location?'location':'calendar'} size={10}/>{item.event.payload?.location||item.event.source_meta?.name||t('calendarUi.timelineImportsLane')}</small>}
   </button>):<span className="family-timeline-free">{t('calendarUi.free')}</span>}
  </div>
 </div>;
}

function TimelineColumns({lanes,days,family,t,language,onOpen,today,rowSize}){
 const timeZone=family?.timezone||'Europe/Berlin';
 const packedByLane=lanes.map(lane=>({lane,items:packEvents(lane.events,days,timeZone)}));
 return <div className="family-timeline-columns" style={{'--timeline-lane-count':lanes.length,'--timeline-row-height':`${rowSize}px`}}>
  <div className="family-timeline-column-corner">{t('calendarUi.timelineDaysLabel')}</div>
  {lanes.map((lane,index)=><div key={lane.id} data-lane-id={lane.id} className={`family-timeline-column-head is-${lane.kind}`} style={{gridColumn:index+2,gridRow:1,'--lane-color':lane.color||'var(--brand)'}}><LaneLabel lane={lane} compact/></div>)}
  {days.map((day,dayIndex)=><div key={`day-${day}`} className={`family-timeline-date-label ${day===today?'is-today':''}`} style={{gridColumn:1,gridRow:dayIndex+2}}><span>{weekday(day,language)}</span><strong>{Number(day.slice(-2))}</strong><small>{month(day,language)}</small></div>)}
  {days.flatMap((day,dayIndex)=>lanes.map((lane,laneIndex)=><span key={`${day}-${lane.id}`} className={`family-timeline-column-cell ${day===today?'is-today':''}`} style={{gridColumn:laneIndex+2,gridRow:dayIndex+2}} aria-hidden="true"/>))}
  {packedByLane.flatMap(({lane,items},laneIndex)=>items.map(item=><button key={`${lane.id}-${item.event.id}-${item.start}`} className={`family-timeline-vertical-event is-${lane.kind}`} style={{gridColumn:laneIndex+2,gridRow:`${item.start+2} / ${item.end+3}`,'--event-level':item.level,...timelineEventStyle(item.event,lane)}} onClick={()=>onOpen(item.event)} title={timelineTitle(item.event,language,t)}><span>{eventTimeLabel(item.event,language,t,item.span)}</span><strong>{item.event.title}</strong>{lane.kind==='ics'&&<small>{item.event.source_meta?.name}</small>}</button>))}
 </div>;
}

function LaneLabel({lane,compact=false}){return <div className={`family-timeline-label ${compact?'compact':''}`}>{lane.kind==='member'?<MemberAvatar person={lane.member} color={lane.color} size={compact?30:38}/>:<span className={`family-timeline-family-avatar is-${lane.kind}`}><Icon name={lane.kind==='ics'?'calendar':'members'}/></span>}<span className="family-timeline-person-copy"><strong>{lane.name}</strong><small>{lane.subtitle}</small></span></div>}
function DayHead({day,today,language}){return <div className={`family-timeline-day-head ${day===today?'is-today':''}`}><span>{weekday(day,language)}</span><strong>{Number(day.slice(-2))}</strong><small>{month(day,language)}</small></div>}

function buildLanes(days,events,family,timeZone,t){
 const familyEvents=[];const importEvents=[];
 const byMember=new Map((family?.memberships||[]).map(member=>[String(member.id),[]]));
 for(const event of events){
  const dayKeys=eventDayKeys(event,timeZone);if(!dayKeys.some(day=>days.includes(day)))continue;
  const members=eventMemberDescriptors(event,family);const imported=event?.source_meta?.kind==='ics';
  if(members.length){for(const descriptor of members){const bucket=byMember.get(String(descriptor.id));if(bucket)bucket.push(event)}if(event.is_family_event&&!imported)familyEvents.push(event);continue}
  if(imported){importEvents.push(event);continue}
  if(event.type==='calendar.event'||event.is_family_event)familyEvents.push(event);
 }
 const lanes=(family?.memberships||[]).map(member=>({id:String(member.id),kind:'member',member,name:membershipDisplayName(member)||member.username||'Person',subtitle:t(member.role)||member.role||'',color:membershipCalendarColor(member),events:byMember.get(String(member.id))||[]}));
 lanes.push({id:FAMILY_LANE,kind:'family',name:family?.name||t('calendarUi.sourceFamily'),subtitle:t('calendarUi.timelineFamilyLane'),color:'var(--brand)',events:uniqueEvents(familyEvents)});
 lanes.push({id:ICS_LANE,kind:'ics',name:t('calendarUi.timelineImportsLane'),subtitle:t('calendarUi.timelineImportsHint'),color:'var(--color-info)',events:uniqueEvents(importEvents)});
 return lanes;
}

function timelineEventStyle(event,lane){if(lane.kind!=='ics')return{'--timeline-event-color':lane.color||'var(--brand)'};const source=eventSourceStyle(event);return{'--timeline-event-color':source['--event-tone']||'var(--color-info)','--timeline-event-soft':source['--event-soft']||'var(--color-info-soft)'}}
function uniqueEvents(events){const seen=new Set();return events.filter(event=>{const key=String(event.id);if(seen.has(key))return false;seen.add(key);return true})}
function packEvents(events,days,timeZone){
 const dayIndex=new Map(days.map((day,index)=>[day,index]));const items=[];
 for(const event of events){const keys=eventDayKeys(event,timeZone).filter(key=>dayIndex.has(key));if(!keys.length)continue;const indexes=keys.map(key=>dayIndex.get(key));items.push({event,start:Math.min(...indexes),end:Math.max(...indexes),span:keys.length})}
 items.sort((a,b)=>a.start-b.start||a.end-b.end||new Date(a.event.starts_at||0)-new Date(b.event.starts_at||0));
 const levelEnds=[];for(const item of items){let level=levelEnds.findIndex(end=>end<item.start);if(level<0)level=levelEnds.length;levelEnds[level]=item.end;item.level=level}return items;
}
function estimateVisibleDays({orientation,viewport,daySize,rowSize,total}){if(!total)return 0;if(!viewport.width)return Math.min(7,total);if(orientation==='columns'){const available=Math.max(rowSize,Math.min(viewport.height||520,760)-62);return clamp(Math.floor(available/rowSize),1,total)}const stickyWidth=viewport.width<=500?112:164;return clamp(Math.floor(Math.max(daySize,viewport.width-stickyWidth)/daySize),1,total)}
function readTimelineSettings(){try{return JSON.parse(window.localStorage.getItem(SETTINGS_KEY)||'{}')||{}}catch{return{}}}
function writeTimelineSettings(value){try{window.localStorage.setItem(SETTINGS_KEY,JSON.stringify(value))}catch{}}
function eventTimeLabel(event,language,t,span){if(event.payload?.all_day)return t('calendarUi.allDay');const start=formatDateTime(language,event.starts_at,{hour:'2-digit',minute:'2-digit'});if(span>1)return `${start} · ${span} ${t('calendarUi.timelineDaysShort')}`;return start}
function timelineTitle(event,language,t){const start=event.payload?.all_day?t('calendarUi.allDay'):formatDateTime(language,event.starts_at,{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});return `${start} · ${event.title}`}
function weekday(day,language){return formatDateTime(language,parseDay(day),{weekday:'short'})}
function month(day,language){return formatDateTime(language,parseDay(day),{month:'short'})}
function parseDay(key){const [year,monthValue,day]=String(key).split('-').map(Number);return new Date(Date.UTC(year,monthValue-1,day,12))}
