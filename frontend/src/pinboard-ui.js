import {isHolidayEvent} from './calendar-event-ui';

export function pinAuthorHue(value){
 const text=String(value||'');let hash=17;
 for(let index=0;index<text.length;index++)hash=(hash*31+text.charCodeAt(index))>>>0;
 return hash%360;
}

export function pinAuthorInitial(name){
 const value=String(name||'?').trim();
 return (value[0]||'?').toUpperCase();
}

export function pinIconName(kind,event){
 if(kind==='event'&&isHolidayEvent(event))return 'school';
 if(kind==='event')return 'calendar';
 if(kind==='task')return 'tasks';
 if(kind==='routine')return 'history';
 if(kind==='shopping'||kind==='shopping_list')return 'shopping';
 if(kind==='photo')return 'camera';
 if(kind==='trip')return 'route';
 if(kind==='document')return 'lists';
 if(kind==='note_ref')return 'lists';
 return 'light';
}

export function pinTypeLabel(kind,de,event){
 if(kind==='event'&&isHolidayEvent(event))return de?'Ferien':'School holidays';
 const labels=de?{
  note:'Notizzettel',photo:'Foto',event:'Termin',task:'Aufgabe',routine:'Routine',note_ref:'Notiz',shopping:'Einkaufsartikel',shopping_list:'Einkaufsliste',trip:'Reise',document:'Dokument'
 }:{
  note:'Note',photo:'Photo',event:'Event',task:'Task',routine:'Routine',note_ref:'Note',shopping:'Shopping item',shopping_list:'Shopping list',trip:'Trip',document:'Document'
 };
 return labels[kind]||labels.note;
}

function civilDate(value){
 if(!value)return null;
 const [year,month,day]=String(value).slice(0,10).split('-').map(Number);
 if(!year||!month||!day)return null;
 return new Date(Date.UTC(year,month-1,day,12));
}

function dateOnly(value,language){
 const date=value instanceof Date?value:new Date(value);
 if(!date||Number.isNaN(date.getTime()))return '';
 return new Intl.DateTimeFormat(language?.startsWith('en')?'en-GB':'de-DE',{timeZone:'UTC',day:'2-digit',month:'short',year:'numeric'}).format(date);
}

export function formatPinEventMeta(event,language='de'){
 if(!event)return '';
 if(isHolidayEvent(event)){
  const start=civilDate(event.payload?.date_start)||civilDate(event.starts_at);
  let end=civilDate(event.payload?.date_end_exclusive);
  if(end&&event.payload?.date_end_exclusive)end.setUTCDate(end.getUTCDate()-1);
  if(!end)end=civilDate(event.ends_at)||start;
  const startLabel=dateOnly(start,language),endLabel=dateOnly(end,language);
  return [startLabel,endLabel].filter(Boolean).join(' – ');
 }
 if(!event.starts_at)return '';
 const start=new Date(event.starts_at);
 if(Number.isNaN(start.getTime()))return '';
 return start.toLocaleString(language?.startsWith('en')?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'});
}
