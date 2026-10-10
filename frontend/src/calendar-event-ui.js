import {isWasteEvent,wasteClass} from './waste-ui';

export const isHolidayEvent=event=>event?.type==='school.holiday';
export const isWarningEvent=event=>Boolean(event?.type?.includes('warning'));
export const isBirthdayEvent=event=>event?.type==='birthday';
export const isNativeCalendarEvent=event=>!event?.source&&event?.type==='calendar.event';

export function eventSourceKey(event){
 if(isBirthdayEvent(event))return 'birthday';
 if(isNativeCalendarEvent(event))return 'family';
 if(isWarningEvent(event))return 'warning';
 if(isWasteEvent(event))return 'waste';
 if(event?.type?.includes('weather'))return 'weather';
 if(event?.type?.includes('transit'))return 'transit';
 if(event?.type?.includes('school'))return 'school';
 return 'calendar';
}

export function eventMarker(event){
 if(isHolidayEvent(event))return {kind:'holiday',icon:'school',className:'marker-holiday'};
 if(isWasteEvent(event))return {kind:'waste',icon:'waste',className:`marker-waste ${wasteClass(event)}`};
 if(isBirthdayEvent(event))return {kind:'birthday',icon:'calendar',className:'marker-birthday'};
 if(isWarningEvent(event))return {kind:'warning',icon:'warning',className:'marker-warning'};
 if(event?.type?.includes('school'))return {kind:'school',icon:'school',className:'marker-school'};
 if(event?.type?.includes('transit'))return {kind:'transit',icon:'transit',className:'marker-transit'};
 if(event?.type?.includes('weather'))return {kind:'weather',icon:'weather',className:'marker-weather'};
 if(event?.type?.startsWith('travel.'))return {kind:'travel',icon:'route',className:'marker-travel'};
 return {kind:'event',icon:'calendar',className:'marker-event'};
}

export function zonedDateKey(value,timeZone='UTC'){
 if(!value)return '';
 const date=value instanceof Date?value:new Date(value);
 if(Number.isNaN(date.getTime()))return '';
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date);
 const read=type=>parts.find(part=>part.type===type)?.value||'';
 return `${read('year')}-${read('month')}-${read('day')}`;
}

export function currentWeek(timeZone='UTC',now=new Date()){
 const todayKey=zonedDateKey(now,timeZone);
 const [year,month,day]=todayKey.split('-').map(Number);
 const anchor=new Date(Date.UTC(year,month-1,day,12));
 const mondayOffset=(anchor.getUTCDay()+6)%7;
 const monday=new Date(anchor);monday.setUTCDate(anchor.getUTCDate()-mondayOffset);
 return Array.from({length:7},(_,index)=>{
  const date=new Date(monday);date.setUTCDate(monday.getUTCDate()+index);
  const key=`${date.getUTCFullYear()}-${String(date.getUTCMonth()+1).padStart(2,'0')}-${String(date.getUTCDate()).padStart(2,'0')}`;
  return {key,date,current:key===todayKey};
 });
}

export function isoWeekNumber(date){
 const value=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),date.getUTCDate()));
 const weekday=value.getUTCDay()||7;
 value.setUTCDate(value.getUTCDate()+4-weekday);
 const yearStart=new Date(Date.UTC(value.getUTCFullYear(),0,1));
 return Math.ceil((((value-yearStart)/86400000)+1)/7);
}

function eachCivilDay(start,endExclusive){
 if(!start)return [];
 const [sy,sm,sd]=start.split('-').map(Number);
 if(!sy||!sm||!sd)return [];
 const cursor=new Date(Date.UTC(sy,sm-1,sd,12));
 const end=endExclusive?new Date(`${endExclusive}T12:00:00Z`):null;
 const values=[];
 for(let guard=0;guard<370;guard++){
  if(end&&cursor>=end)break;
  values.push(`${cursor.getUTCFullYear()}-${String(cursor.getUTCMonth()+1).padStart(2,'0')}-${String(cursor.getUTCDate()).padStart(2,'0')}`);
  if(!end)break;
  cursor.setUTCDate(cursor.getUTCDate()+1);
 }
 return values;
}

export function eventDayKeys(event,timeZone='UTC'){
 const civilStart=event?.payload?.date_start;
 const civilEnd=event?.payload?.date_end_exclusive;
 if(civilStart)return eachCivilDay(civilStart,civilEnd);
 const start=zonedDateKey(event?.starts_at,timeZone);
 if(!start)return [];
 const end=zonedDateKey(event?.ends_at,timeZone);
 if(!end||end===start)return [start];
 const keys=eachCivilDay(start,null);
 const [sy,sm,sd]=start.split('-').map(Number);
 const [ey,em,ed]=end.split('-').map(Number);
 const cursor=new Date(Date.UTC(sy,sm-1,sd,12));
 const endDate=new Date(Date.UTC(ey,em-1,ed,12));
 const result=[];
 for(let guard=0;guard<370&&cursor<=endDate;guard++){
  result.push(`${cursor.getUTCFullYear()}-${String(cursor.getUTCMonth()+1).padStart(2,'0')}-${String(cursor.getUTCDate()).padStart(2,'0')}`);
  cursor.setUTCDate(cursor.getUTCDate()+1);
 }
 return result.length?result:keys;
}

export function eventVisibleInWeek(event,settings={events:true,waste:true,holidays:true,special:true}){
 const marker=eventMarker(event);
 if(marker.kind==='holiday')return settings.holidays!==false;
 if(marker.kind==='waste')return settings.waste!==false;
 if(marker.kind==='event')return settings.events!==false;
 return settings.special!==false;
}
