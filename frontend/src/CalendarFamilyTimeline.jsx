import {useMemo} from 'react';
import {Icon} from './icons';
import {formatDateTime} from './locale';
import MemberAvatar from './MemberAvatar';
import {eventDayKeys} from './calendar-event-ui';
import {eventMemberDescriptors,membershipCalendarColor,membershipDisplayName} from './calendar-members';
import './calendar-family-timeline.css';

const FAMILY_LANE='__family__';

export default function CalendarFamilyTimeline({days,events,family,t,language,onOpen,today}){
 const timeZone=family?.timezone||'Europe/Berlin';
 const lanes=useMemo(()=>buildLanes(days,events,family,timeZone),[days,events,family,timeZone]);
 const dayWidth=language?.startsWith('de')?'112px':'118px';
 return <section className="calendar-view family-timeline" aria-label={t('calendarUi.viewTimeline')}>
  <div className="family-timeline-intro"><div><strong>{t('calendarUi.timelineTitle')}</strong><span>{t('calendarUi.timelineHint')}</span></div><span className="family-timeline-week-badge"><Icon name="members"/>{t('calendarUi.timelinePeople',{count:Math.max(0,lanes.length-1)})}</span></div>
  <div className="family-timeline-scroll" tabIndex="0" aria-label={t('calendarUi.timelineScrollHint')}>
   <div className="family-timeline-table" style={{'--timeline-day-width':dayWidth}}>
    <div className="family-timeline-header family-timeline-row">
     <div className="family-timeline-label family-timeline-corner"><span>{t('calendarUi.timelinePeopleLabel')}</span></div>
     <div className="family-timeline-days">{days.map(day=><div key={day} className={`family-timeline-day-head ${day===today?'is-today':''}`}><span>{weekday(day,language)}</span><strong>{Number(day.slice(-2))}</strong><small>{month(day,language)}</small></div>)}</div>
    </div>
    {lanes.map(lane=><TimelineLane key={lane.id} lane={lane} days={days} family={family} t={t} language={language} onOpen={onOpen}/>) }
   </div>
  </div>
 </section>;
}

function TimelineLane({lane,days,family,t,language,onOpen}){
 const packed=packEvents(lane.events,days,family?.timezone||'Europe/Berlin');
 const rows=Math.max(1,...packed.map(item=>item.level+1));
 const minHeight=Math.max(72,rows*46+20);
 return <div className={`family-timeline-row family-timeline-lane ${lane.id===FAMILY_LANE?'is-family-lane':''}`} style={{'--lane-color':lane.color||'var(--brand)','--timeline-lane-height':`${minHeight}px`}}>
  <div className="family-timeline-label">
   {lane.id===FAMILY_LANE?<span className="family-timeline-family-avatar"><Icon name="members"/></span>:<MemberAvatar person={lane.member} color={lane.color} size={38}/>} 
   <span className="family-timeline-person-copy"><strong>{lane.name}</strong><small>{lane.id===FAMILY_LANE?t('calendarUi.timelineFamilyLane'):t(lane.member?.role)||lane.member?.role}</small></span>
  </div>
  <div className="family-timeline-track" style={{'--timeline-rows':rows}}>
   {days.map(day=><span key={day} className="family-timeline-grid-cell" aria-hidden="true"/>)}
   {packed.length?packed.map(item=><button key={`${lane.id}-${item.event.id}-${item.start}`} className="family-timeline-event" style={{gridColumn:`${item.start+1} / ${item.end+2}`,gridRow:item.level+1}} onClick={()=>onOpen(item.event)} title={timelineTitle(item.event,language,t)}>
    <span className="family-timeline-event-time">{eventTimeLabel(item.event,language,t,item.span)}</span>
    <strong>{item.event.title}</strong>
    {item.event.payload?.location&&<small><Icon name="location" size={10}/>{item.event.payload.location}</small>}
   </button>):<span className="family-timeline-free">{t('calendarUi.free')}</span>}
  </div>
 </div>;
}

function buildLanes(days,events,family,timeZone){
 const familyEvents=[];
 const byMember=new Map((family?.memberships||[]).map(member=>[String(member.id),[]]));
 for(const event of events){
  const dayKeys=eventDayKeys(event,timeZone);
  if(!dayKeys.some(day=>days.includes(day)))continue;
  const members=eventMemberDescriptors(event,family);
  if(members.length){for(const descriptor of members){const bucket=byMember.get(String(descriptor.id));if(bucket)bucket.push(event)}}
  if((!members.length&&event.type==='calendar.event')||event.is_family_event)familyEvents.push(event);
 }
 const lanes=(family?.memberships||[]).map(member=>({id:String(member.id),member,name:membershipDisplayName(member)||member.username||'Person',color:membershipCalendarColor(member),events:byMember.get(String(member.id))||[]}));
 lanes.push({id:FAMILY_LANE,name:family?.name||'Familie',color:'var(--brand)',events:uniqueEvents(familyEvents)});
 return lanes;
}

function uniqueEvents(events){const seen=new Set();return events.filter(event=>{const key=String(event.id);if(seen.has(key))return false;seen.add(key);return true})}
function packEvents(events,days,timeZone){
 const dayIndex=new Map(days.map((day,index)=>[day,index]));
 const items=[];
 for(const event of events){
  const keys=eventDayKeys(event,timeZone).filter(key=>dayIndex.has(key));
  if(!keys.length)continue;
  const indexes=keys.map(key=>dayIndex.get(key));
  items.push({event,start:Math.min(...indexes),end:Math.max(...indexes),span:keys.length});
 }
 items.sort((a,b)=>a.start-b.start||a.end-b.end||new Date(a.event.starts_at||0)-new Date(b.event.starts_at||0));
 const levelEnds=[];
 for(const item of items){let level=levelEnds.findIndex(end=>end<item.start);if(level<0)level=levelEnds.length;levelEnds[level]=item.end;item.level=level}
 return items;
}
function eventTimeLabel(event,language,t,span){if(event.payload?.all_day)return t('calendarUi.allDay');const start=formatDateTime(language,event.starts_at,{hour:'2-digit',minute:'2-digit'});if(span>1)return `${start} · ${span} ${t('calendarUi.timelineDaysShort')}`;return start}
function timelineTitle(event,language,t){const start=event.payload?.all_day?t('calendarUi.allDay'):formatDateTime(language,event.starts_at,{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});return `${start} · ${event.title}`}
function weekday(day,language){return formatDateTime(language,parseDay(day),{weekday:'short'})}
function month(day,language){return formatDateTime(language,parseDay(day),{month:'short'})}
function parseDay(key){const [year,monthValue,day]=String(key).split('-').map(Number);return new Date(Date.UTC(year,monthValue-1,day,12))}
