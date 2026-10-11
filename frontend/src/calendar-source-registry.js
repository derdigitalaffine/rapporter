import {eventSourceKey} from './calendar-event-ui';

export const CALENDAR_SOURCE_REGISTRY={
 birthday:{icon:'calendar',color:'purple',labelKey:null},
 family:{icon:'members',color:'green',labelKey:'sourceFamily'},
 warning:{icon:'warning',color:'red',labelKey:'sourceWarnings'},
 waste:{icon:'waste',color:'orange',labelKey:'sourceWaste'},
 weather:{icon:'weather',color:'blue',labelKey:'sourceWeather'},
 transit:{icon:'transit',color:'purple',labelKey:'sourceTransit'},
 school:{icon:'school',color:'purple',labelKey:'sourceSchool'},
 calendar:{icon:'calendar',color:'blue',labelKey:'sourceCalendar'},
};

const TONES={
 blue:{tone:'var(--brand)',soft:'var(--soft)'},
 green:{tone:'var(--positive)',soft:'var(--green-soft)'},
 purple:{tone:'#7655a5',soft:'#f2edff'},
 orange:{tone:'var(--color-warning)',soft:'var(--color-warning-soft)'},
 red:{tone:'#a33e3e',soft:'#fff0f0'},
 teal:{tone:'#237a7a',soft:'#e9f7f5'},
 slate:{tone:'var(--muted)',soft:'var(--soft)'},
};

export function calendarSourceLabel(key,t,family){
 const entry=CALENDAR_SOURCE_REGISTRY[key]||CALENDAR_SOURCE_REGISTRY.calendar;
 if(key==='birthday')return t?.('birthdayUi.title')||'Birthday';
 if(key==='family')return family?.name||t?.('calendarUi.sourceFamily')||'FamilyOS';
 return t?.(`calendarUi.${entry.labelKey||'sourceCalendar'}`)||'Calendar';
}

export function calendarSourceIdentity(event){
 const semantic=eventSourceKey(event);
 if(semantic==='calendar'&&event?.source&&['ics','generic'].includes(event?.source_kind))return `integration:${event.source}`;
 return semantic;
}

export function calendarSourceMeta(event,{family,t}={}){
 const semantic=eventSourceKey(event);
 const base=CALENDAR_SOURCE_REGISTRY[semantic]||CALENDAR_SOURCE_REGISTRY.calendar;
 const distinct=semantic==='calendar'&&event?.source&&['ics','generic'].includes(event?.source_kind);
 const presentation=event?.source_presentation||{};
 return {
  identity:calendarSourceIdentity(event),
  semantic,
  icon:distinct?(presentation.icon||base.icon):base.icon,
  color:distinct?(presentation.color||base.color):base.color,
  label:distinct?(presentation.label||event.source_name||calendarSourceLabel(semantic,t,family)):calendarSourceLabel(semantic,t,family),
 };
}

export function sourceToneVariables(color){
 const tone=TONES[color]||TONES.blue;
 return {'--event-tone':tone.tone,'--event-soft':tone.soft};
}

export function sourceBadgeStyle(color){
 const tone=TONES[color]||TONES.blue;
 return {color:tone.tone,background:tone.soft};
}
