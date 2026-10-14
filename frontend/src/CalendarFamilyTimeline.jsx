import {useEffect,useMemo,useRef,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {formatDateTime} from './locale';
import MemberAvatar from './MemberAvatar';
import {eventDayKeys,eventSourceStyle} from './calendar-event-ui';
import {eventMemberDescriptors,membershipCalendarColor,membershipDisplayName} from './calendar-members';
import './calendar-family-timeline.css';
import './calendar-family-timeline-advanced.css';

const FAMILY_LANE='__family__';
const ICS_LANE='__ics__';
const LEGACY_SETTINGS_KEY='familyos:calendar:timeline:v2';
const SETTINGS_KEY_PREFIX='familyos:calendar:timeline:v3';
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
const settingNumber=(value,fallback,min,max)=>{const parsed=Number(value);return Number.isFinite(parsed)?clamp(parsed,min,max):fallback};

export default function CalendarFamilyTimeline({days,events,family,t,language,onOpen,today}){
 const timeZone=family?.timezone||'Europe/Berlin';
 const settingsKey=timelineSettingsKey(family);
 const initialSettings=useMemo(()=>{const scoped=settingsKey?readTimelineSettings(settingsKey):{};return hasSettings(scoped)?scoped:readTimelineSettings(LEGACY_SETTINGS_KEY)},[]);
 const [orientation,setOrientation]=useState(initialSettings.orientation==='columns'?'columns':'rows');
 const [zoom,setZoom]=useState(()=>settingNumber(initialSettings.zoom,48,0,200));
 const [laneDensity,setLaneDensity]=useState(()=>settingNumber(initialSettings.laneDensity,18,0,100));
 const [hiddenLaneIds,setHiddenLaneIds]=useState(()=>new Set(Array.isArray(initialSettings.hiddenLaneIds)?initialSettings.hiddenLaneIds.map(String):[]));
 const [laneOrder,setLaneOrder]=useState(()=>Array.isArray(initialSettings.laneOrder)?initialSettings.laneOrder.map(String):[]);
 const [hideEmptyLanes,setHideEmptyLanes]=useState(Boolean(initialSettings.hideEmptyLanes));
 const [laneQuery,setLaneQuery]=useState('');
 const [draggedLaneId,setDraggedLaneId]=useState('');
 const [activeSettingsKey,setActiveSettingsKey]=useState('');
 const [viewport,setViewport]=useState({width:0,height:0});
 const scrollRef=useRef(null);
 const laneOrderTouchedRef=useRef(false);
 const lanes=useMemo(()=>buildLanes(days,events,family,timeZone,t),[days,events,family,timeZone,t]);
 const laneIdsKey=useMemo(()=>lanes.map(lane=>lane.id).join('\u001f'),[lanes]);
 const orderedLanes=useMemo(()=>orderLanes(lanes,laneOrder),[lanes,laneOrder]);
 const visibleLanes=useMemo(()=>orderedLanes.filter(lane=>!hiddenLaneIds.has(lane.id)&&(!hideEmptyLanes||lane.events.length>0)),[orderedLanes,hiddenLaneIds,hideEmptyLanes]);
 const laneControls=useMemo(()=>{const query=laneQuery.trim().toLocaleLowerCase(language||undefined);if(!query)return orderedLanes;return orderedLanes.filter(lane=>`${lane.name} ${lane.subtitle}`.toLocaleLowerCase(language||undefined).includes(query))},[orderedLanes,laneQuery,language]);
 const daySize=32+(zoom*1.4);
 const timeRowSize=28+(zoom*.46);
 const laneBaseHeight=40+(laneDensity*.42);
 const eventRowHeight=26+(laneDensity*.24);
 const laneGap=3+(laneDensity*.03);
 const visibleDays=useMemo(()=>estimateVisibleDays({orientation,viewport,daySize,rowSize:timeRowSize,total:days.length}),[orientation,viewport,daySize,timeRowSize,days.length]);
 const peopleCount=visibleLanes.filter(lane=>lane.kind==='member').length;
 const nowPosition=useMemo(()=>timelineNowPosition(days,timeZone),[days,timeZone,today]);
 useEffect(()=>{
  if(!settingsKey||activeSettingsKey===settingsKey)return;
  const saved=readTimelineSettings(settingsKey);
  if(hasSettings(saved)){
   setOrientation(saved.orientation==='columns'?'columns':'rows');
   setZoom(settingNumber(saved.zoom,48,0,200));
   setLaneDensity(settingNumber(saved.laneDensity,18,0,100));
   setHiddenLaneIds(new Set(Array.isArray(saved.hiddenLaneIds)?saved.hiddenLaneIds.map(String):[]));
   setLaneOrder(Array.isArray(saved.laneOrder)?saved.laneOrder.map(String):[]);
   setHideEmptyLanes(Boolean(saved.hideEmptyLanes));
  }
  setActiveSettingsKey(settingsKey);
 },[settingsKey,activeSettingsKey]);
 useEffect(()=>{
  if(!activeSettingsKey)return;
  writeTimelineSettings(activeSettingsKey,{orientation,zoom,laneDensity,hiddenLaneIds:[...hiddenLaneIds],laneOrder,hideEmptyLanes});
 },[activeSettingsKey,orientation,zoom,laneDensity,hiddenLaneIds,laneOrder,hideEmptyLanes]);
 useEffect(()=>{setLaneOrder(current=>{const next=normalizeLaneOrder(current,lanes.map(lane=>lane.id));return arraysEqual(next,current)?current:next})},[laneIdsKey]);
 useEffect(()=>{laneOrderTouchedRef.current=false},[family?.id]);
 useEffect(()=>{
  let live=true;
  if(!family?.id||!settingsKey)return()=>{live=false};
  api(`/calendar-planner-preferences/?family=${encodeURIComponent(family.id)}`).then(value=>{
   if(!live||laneOrderTouchedRef.current)return;
   const serverOrder=Array.isArray(value?.lane_order)?value.lane_order.map(String):[];
   if(serverOrder.length){setLaneOrder(serverOrder);return}
   const local=readTimelineSettings(settingsKey);
   const fallback=Array.isArray(local.laneOrder)?local.laneOrder.map(String):[];
   if(fallback.length)persistLaneOrder(fallback);
  }).catch(()=>{});
  return()=>{live=false};
 },[family?.id,settingsKey]);
 useEffect(()=>{
  const node=scrollRef.current;if(!node)return;
  const update=()=>setViewport({width:node.clientWidth,height:node.clientHeight});update();
  if(typeof ResizeObserver==='undefined')return;
  const observer=new ResizeObserver(update);observer.observe(node);return()=>observer.disconnect();
 },[orientation]);
 function toggleLane(id){setHiddenLaneIds(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next})}
 function showAll(){setHiddenLaneIds(new Set());setHideEmptyLanes(false)}
 function persistLaneOrder(next){if(!family?.id)return;api(`/calendar-planner-preferences/?family=${encodeURIComponent(family.id)}`,{method:'PATCH',body:JSON.stringify({family:String(family.id),lane_order:next})}).catch(()=>{})}
 function moveLane(id,direction){const next=moveLaneOrder(laneOrder,lanes.map(lane=>lane.id),id,direction);laneOrderTouchedRef.current=true;setLaneOrder(next);persistLaneOrder(next)}
 function dropLane(targetId){if(!draggedLaneId||draggedLaneId===targetId){setDraggedLaneId('');return}const next=dropLaneOrder(laneOrder,lanes.map(lane=>lane.id),draggedLaneId,targetId);laneOrderTouchedRef.current=true;setLaneOrder(next);persistLaneOrder(next);setDraggedLaneId('')}
 return <section className={`calendar-view family-timeline orientation-${orientation}`} aria-label={t('calendarUi.viewTimeline')}>
  <div className="family-timeline-intro"><div><strong>{t('calendarUi.timelineTitle')}</strong><span>{t('calendarUi.timelineHint')}</span></div><span className="family-timeline-week-badge"><Icon name="members"/>{t('calendarUi.timelinePeople',{count:peopleCount})}</span></div>
  <div className="family-timeline-controls" role="toolbar" aria-label={t('calendarUi.timelineControls')}>
   <div className="family-timeline-orientation" role="group" aria-label={t('calendarUi.timelineOrientation')}>
    <button type="button" aria-pressed={orientation==='rows'} className={orientation==='rows'?'active':''} onClick={()=>setOrientation('rows')}><Icon name="members"/>{t('calendarUi.timelineOrientationRows')}</button>
    <button type="button" aria-pressed={orientation==='columns'} className={orientation==='columns'?'active':''} onClick={()=>setOrientation('columns')}><Icon name="refresh"/>{t('calendarUi.timelineOrientationColumns')}</button>
   </div>
   <label className="family-timeline-zoom"><span><Icon name="search"/>{t('calendarUi.timelineZoom')}</span><input type="range" min="0" max="200" step="1" value={zoom} onChange={event=>setZoom(Number(event.target.value))}/><output>{t('calendarUi.timelineVisibleDays',{count:visibleDays})}</output></label>
   <label className="family-timeline-zoom family-timeline-density"><span><Icon name="members"/>{t('calendarUi.timelineRowHeight')}</span><input type="range" min="0" max="100" step="1" value={laneDensity} onChange={event=>setLaneDensity(Number(event.target.value))}/><output>{Math.round(laneBaseHeight)} px</output></label>
   <details className="family-timeline-lane-picker"><summary><Icon name="members"/><span>{t('calendarUi.timelineLanes')}</span><strong>{visibleLanes.length}/{lanes.length}</strong></summary><div className="family-timeline-lane-controls">
    <div className="family-timeline-lane-controls-head"><span>{t('calendarUi.timelineLanesHint')}</span>{(hiddenLaneIds.size>0||hideEmptyLanes)&&<button type="button" className="text-link" onClick={showAll}>{t('calendarUi.timelineShowAll')}</button>}</div>
    <div className="family-timeline-lane-tools"><label className="family-timeline-lane-search"><Icon name="search"/><span className="sr-only">{t('calendarUi.timelineLaneSearch')}</span><input type="search" value={laneQuery} onChange={event=>setLaneQuery(event.target.value)} placeholder={t('calendarUi.timelineLaneSearch')}/></label><label className="family-timeline-empty-toggle"><input type="checkbox" checked={hideEmptyLanes} onChange={event=>setHideEmptyLanes(event.target.checked)}/><span>{t('calendarUi.timelineHideEmpty')}</span></label></div>
    <p className="family-timeline-reorder-hint"><Icon name="drag"/>{t('calendarUi.timelineReorderHint')}</p>
    {laneControls.map(lane=>{const orderIndex=orderedLanes.findIndex(item=>item.id===lane.id);return <div key={lane.id} className={`family-timeline-lane-toggle family-timeline-lane-order-item ${draggedLaneId===lane.id?'is-dragging':''}`} draggable onDragStart={event=>{setDraggedLaneId(lane.id);event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',lane.id)}} onDragOver={event=>{event.preventDefault();event.dataTransfer.dropEffect='move'}} onDrop={event=>{event.preventDefault();dropLane(lane.id)}} onDragEnd={()=>setDraggedLaneId('')}>
     <span className="family-timeline-lane-drag" aria-hidden="true"><Icon name="drag"/></span>
     {lane.kind==='member'?<MemberAvatar person={lane.member} color={lane.color} size={28}/>:<span className={`family-timeline-control-icon is-${lane.kind}`}><Icon name={lane.kind==='ics'?'calendar':'members'}/></span>}
     <span className="grow"><strong>{lane.name}</strong><small>{lane.subtitle}</small></span>
     <span className="family-timeline-lane-order-actions"><button type="button" disabled={orderIndex===0} onClick={()=>moveLane(lane.id,-1)} aria-label={t('calendarUi.timelineMoveUp',{name:lane.name})}>↑</button><button type="button" disabled={orderIndex===orderedLanes.length-1} onClick={()=>moveLane(lane.id,1)} aria-label={t('calendarUi.timelineMoveDown',{name:lane.name})}>↓</button><label className="family-timeline-lane-visible"><span className="sr-only">{t('calendarUi.timelineToggleLane',{name:lane.name})}</span><input type="checkbox" checked={!hiddenLaneIds.has(lane.id)} onChange={()=>toggleLane(lane.id)} aria-label={lane.name}/></label></span>
    </div>})}
   </div></details>
  </div>
  {visibleLanes.length?<div ref={scrollRef} className="family-timeline-scroll" tabIndex="0" aria-label={t(orientation==='rows'?'calendarUi.timelineScrollHint':'calendarUi.timelineScrollHintVertical')}>
   {orientation==='rows'?<TimelineRows lanes={visibleLanes} days={days} family={family} t={t} language={language} onOpen={onOpen} today={today} daySize={daySize} laneBaseHeight={laneBaseHeight} eventRowHeight={eventRowHeight} laneGap={laneGap} laneDensity={laneDensity} nowPosition={nowPosition}/>:<TimelineColumns lanes={visibleLanes} days={days} family={family} t={t} language={language} onOpen={onOpen} today={today} rowSize={timeRowSize} laneDensity={laneDensity}/>} 
  </div>:<div className="family-timeline-empty"><Icon name="members"/><strong>{t('calendarUi.timelineNoLanes')}</strong><button type="button" className="secondary compact" onClick={showAll}>{t('calendarUi.timelineShowAll')}</button></div>}
 </section>;
}

function TimelineRows({lanes,days,family,t,language,onOpen,today,daySize,laneBaseHeight,eventRowHeight,laneGap,laneDensity,nowPosition}){
 return <div className="family-timeline-table family-timeline-rows" style={{'--timeline-day-width':`${daySize}px`,'--timeline-day-count':days.length}}>
  <div className="family-timeline-header family-timeline-row">
   <div className="family-timeline-label family-timeline-corner"><span>{t('calendarUi.timelinePeopleLabel')}</span></div>
   <div className="family-timeline-days">{days.map(day=><DayHead key={day} day={day} today={today} language={language}/>)}</div>
  </div>
  {lanes.map(lane=><TimelineLane key={lane.id} lane={lane} days={days} family={family} t={t} language={language} onOpen={onOpen} laneBaseHeight={laneBaseHeight} eventRowHeight={eventRowHeight} laneGap={laneGap} laneDensity={laneDensity} nowPosition={nowPosition}/>) }
 </div>;
}

function TimelineLane({lane,days,family,t,language,onOpen,laneBaseHeight,eventRowHeight,laneGap,laneDensity,nowPosition}){
 const packed=packEvents(lane.events,days,family?.timezone||'Europe/Berlin');
 const rows=Math.max(1,...packed.map(item=>item.level+1));
 const conflicts=countLaneConflicts(lane.events);
 const minHeight=Math.max(laneBaseHeight,rows*(eventRowHeight+laneGap)+10);
 const eventPadding=Math.max(3,Math.round((eventRowHeight-18)/4));
 return <div data-lane-id={lane.id} className={`family-timeline-row family-timeline-lane is-${lane.kind}`} style={{'--lane-color':lane.color||'var(--brand)','--timeline-lane-height':`${minHeight}px`}}>
  <LaneLabel lane={lane} density={laneDensity} conflictCount={conflicts} t={t}/>
  <div className="family-timeline-track" style={{'--timeline-rows':rows,gridAutoRows:`${eventRowHeight}px`,rowGap:`${laneGap}px`,padding:`${Math.max(4,Math.round(laneGap))}px 0`}}>
   {days.map(day=><span key={day} className={`family-timeline-grid-cell ${isWeekend(day)?'is-weekend':''}`} aria-hidden="true"/>)}
   {Number.isFinite(nowPosition)&&<span className="family-timeline-now-marker" style={{left:`${nowPosition}%`}} title={t('calendarUi.timelineNow')} aria-hidden="true"/>}
   {packed.length?packed.map(item=><button key={`${lane.id}-${item.event.id}-${item.start}`} className="family-timeline-event" style={{gridColumn:`${item.start+1} / ${item.end+2}`,gridRow:item.level+1,minHeight:`${eventRowHeight}px`,padding:`${eventPadding}px 8px`,...timelineEventStyle(item.event,lane)}} onClick={()=>onOpen(item.event)} title={timelineTitle(item.event,language,t)}>
    <span className="family-timeline-event-time">{eventTimeLabel(item.event,language,t,item.span)}</span>
    <strong>{item.event.title}</strong>
    {(item.event.payload?.location||lane.kind==='ics')&&<small><Icon name={item.event.payload?.location?'location':'calendar'} size={10}/>{item.event.payload?.location||item.event.source_meta?.name||t('calendarUi.timelineImportsLane')}</small>}
   </button>):<span className="family-timeline-free">{t('calendarUi.free')}</span>}
  </div>
 </div>;
}

function TimelineColumns({lanes,days,family,t,language,onOpen,today,rowSize,laneDensity}){
 const timeZone=family?.timezone||'Europe/Berlin';
 const packedByLane=lanes.map(lane=>({lane,items:packEvents(lane.events,days,timeZone),conflicts:countLaneConflicts(lane.events)}));
 const headerSize=42+(laneDensity*.18);
 return <div className="family-timeline-columns" style={{'--timeline-lane-count':lanes.length,'--timeline-row-height':`${rowSize}px`,gridTemplateRows:`${headerSize}px repeat(${days.length}, ${rowSize}px)`}}>
  <div className="family-timeline-column-corner">{t('calendarUi.timelineDaysLabel')}</div>
  {packedByLane.map(({lane,conflicts},index)=><div key={lane.id} data-lane-id={lane.id} className={`family-timeline-column-head is-${lane.kind}`} style={{gridColumn:index+2,gridRow:1,'--lane-color':lane.color||'var(--brand)'}}><LaneLabel lane={lane} compact density={laneDensity} conflictCount={conflicts} t={t}/></div>)}
  {days.map((day,dayIndex)=><div key={`day-${day}`} className={`family-timeline-date-label ${day===today?'is-today':''} ${isWeekend(day)?'is-weekend':''}`} style={{gridColumn:1,gridRow:dayIndex+2}}><span>{weekday(day,language)}</span><strong>{Number(day.slice(-2))}</strong><small>{month(day,language)}</small></div>)}
  {days.flatMap((day,dayIndex)=>lanes.map((lane,laneIndex)=><span key={`${day}-${lane.id}`} className={`family-timeline-column-cell ${day===today?'is-today':''} ${isWeekend(day)?'is-weekend':''}`} style={{gridColumn:laneIndex+2,gridRow:dayIndex+2}} aria-hidden="true"/>))}
  {packedByLane.flatMap(({lane,items},laneIndex)=>items.map(item=><button key={`${lane.id}-${item.event.id}-${item.start}`} className={`family-timeline-vertical-event is-${lane.kind}`} style={{gridColumn:laneIndex+2,gridRow:`${item.start+2} / ${item.end+3}`,'--event-level':item.level,...timelineEventStyle(item.event,lane)}} onClick={()=>onOpen(item.event)} title={timelineTitle(item.event,language,t)}><span>{eventTimeLabel(item.event,language,t,item.span)}</span><strong>{item.event.title}</strong>{lane.kind==='ics'&&<small>{item.event.source_meta?.name}</small>}</button>))}
 </div>;
}

function LaneLabel({lane,compact=false,density=18,conflictCount=0,t}){const avatarSize=compact?Math.round(24+density*.05):Math.round(26+density*.08);const padY=Math.round(4+density*.04);return <div className={`family-timeline-label ${compact?'compact':''}`} style={{paddingBlock:`${padY}px`}}>{lane.kind==='member'?<MemberAvatar person={lane.member} color={lane.color} size={avatarSize}/>:<span className={`family-timeline-family-avatar is-${lane.kind}`} style={{width:`${avatarSize}px`,height:`${avatarSize}px`}}><Icon name={lane.kind==='ics'?'calendar':'members'}/></span>}<span className="family-timeline-person-copy"><strong>{lane.name}</strong><small>{lane.subtitle}</small></span>{conflictCount>0&&<span className="family-timeline-conflict" title={t('calendarUi.timelineConflictCount',{count:conflictCount})} aria-label={t('calendarUi.timelineConflictCount',{count:conflictCount})}><Icon name="warning" size={11}/><b>{conflictCount}</b></span>}</div>}
function DayHead({day,today,language}){return <div className={`family-timeline-day-head ${day===today?'is-today':''} ${isWeekend(day)?'is-weekend':''}`}><span>{weekday(day,language)}</span><strong>{Number(day.slice(-2))}</strong><small>{month(day,language)}</small></div>}

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
 const lanes=(family?.memberships||[]).map(member=>({id:String(member.id),kind:'member',member,name:membershipDisplayName(member)||member.username||'Person',subtitle:t(member.role)||member.role||'',color:membershipCalendarColor(member),events:uniqueEvents(byMember.get(String(member.id))||[])}));
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
function countLaneConflicts(events){const ranges=(events||[]).map(event=>({start:Date.parse(event.starts_at||''),end:Date.parse(event.ends_at||event.starts_at||'')})).filter(range=>Number.isFinite(range.start)&&Number.isFinite(range.end)).sort((a,b)=>a.start-b.start||a.end-b.end);let maxEnd=-Infinity;let conflicts=0;for(const range of ranges){if(range.start<maxEnd)conflicts+=1;maxEnd=Math.max(maxEnd,range.end)}return conflicts}
function normalizeLaneOrder(order,ids){const valid=new Set(ids.map(String));const next=[];for(const id of order||[]){const value=String(id);if(valid.has(value)&&!next.includes(value))next.push(value)}for(const id of ids){const value=String(id);if(!next.includes(value))next.push(value)}return next}
function orderLanes(lanes,order){const byId=new Map(lanes.map(lane=>[lane.id,lane]));return normalizeLaneOrder(order,lanes.map(lane=>lane.id)).map(id=>byId.get(id)).filter(Boolean)}
function moveLaneOrder(order,ids,id,direction){const next=normalizeLaneOrder(order,ids);const index=next.indexOf(String(id));const target=index+direction;if(index<0||target<0||target>=next.length)return next;[next[index],next[target]]=[next[target],next[index]];return next}
function dropLaneOrder(order,ids,sourceId,targetId){const next=normalizeLaneOrder(order,ids);const source=next.indexOf(String(sourceId));const target=next.indexOf(String(targetId));if(source<0||target<0||source===target)return next;const [value]=next.splice(source,1);next.splice(target,0,value);return next}
function arraysEqual(a,b){return a.length===b.length&&a.every((value,index)=>value===b[index])}
function estimateVisibleDays({orientation,viewport,daySize,rowSize,total}){if(!total)return 0;if(!viewport.width)return Math.min(7,total);if(orientation==='columns'){const available=Math.max(rowSize,Math.min(viewport.height||520,760)-62);return clamp(Math.floor(available/rowSize),1,total)}const stickyWidth=viewport.width<=500?112:164;return clamp(Math.floor(Math.max(daySize,viewport.width-stickyWidth)/daySize),1,total)}
function timelineSettingsKey(family){if(!family?.id||!family?.current_membership_id)return'';return `${SETTINGS_KEY_PREFIX}:${String(family.id)}:${String(family.current_membership_id)}`}
function hasSettings(value){return Boolean(value&&typeof value==='object'&&Object.keys(value).length)}
function readTimelineSettings(key){if(!key)return{};try{return JSON.parse(window.localStorage.getItem(key)||'{}')||{}}catch{return{}}}
function writeTimelineSettings(key,value){if(!key)return;try{window.localStorage.setItem(key,JSON.stringify(value))}catch{}}
function timelineNowPosition(days,timeZone){try{const parts=new Intl.DateTimeFormat('en-GB',{timeZone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());const get=type=>parts.find(part=>part.type===type)?.value;const key=`${get('year')}-${get('month')}-${get('day')}`;const index=days.indexOf(key);if(index<0)return NaN;const minutes=(Number(get('hour'))*60)+Number(get('minute'));return ((index+(minutes/1440))/days.length)*100}catch{return NaN}}
function isWeekend(day){const value=parseDay(day).getUTCDay();return value===0||value===6}
function eventTimeLabel(event,language,t,span){if(event.payload?.all_day)return t('calendarUi.allDay');const start=formatDateTime(language,event.starts_at,{hour:'2-digit',minute:'2-digit'});if(span>1)return `${start} · ${span} ${t('calendarUi.timelineDaysShort')}`;return start}
function timelineTitle(event,language,t){const start=event.payload?.all_day?t('calendarUi.allDay'):formatDateTime(language,event.starts_at,{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});return `${start} · ${event.title}`}
function weekday(day,language){return formatDateTime(language,parseDay(day),{weekday:'short'})}
function month(day,language){return formatDateTime(language,parseDay(day),{month:'short'})}
function parseDay(key){const [year,monthValue,day]=String(key).split('-').map(Number);return new Date(Date.UTC(year,monthValue-1,day,12))}