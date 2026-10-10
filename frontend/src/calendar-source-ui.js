import {eventSourceKey} from './calendar-event-ui';

export const CALENDAR_COLORS=['blue','teal','green','amber','orange','red','pink','purple','slate'];
export const CALENDAR_ICONS=['calendar','school','waste','weather','transit','members','user','heart','pet','baby','location','clock','tags','info'];

const fallback={
 birthday:{color:'pink',icon:'calendar'},family:{color:'teal',icon:'members'},warning:{color:'red',icon:'warning'},
 waste:{color:'green',icon:'waste'},weather:{color:'blue',icon:'weather'},transit:{color:'purple',icon:'transit'},
 school:{color:'amber',icon:'school'},calendar:{color:'blue',icon:'calendar'}
};

export function sourceIdentity(event){
 if(event?.source)return `source:${event.source}`;
 return eventSourceKey(event);
}

export function sourceDescriptor(event,sources=[],family,t){
 const category=eventSourceKey(event);
 const source=event?.source?sources.find(item=>String(item.id)===String(event.source)):null;
 const appearance=source?.config?.appearance||{};
 const base=fallback[category]||fallback.calendar;
 const labelKeys={birthday:'sourceBirthdays',family:'sourceFamily',warning:'sourceWarnings',waste:'sourceWaste',weather:'sourceWeather',transit:'sourceTransit',school:'sourceSchool',calendar:'sourceCalendar'};
 const fallbackLabel=category==='family'?(family?.name||t('calendarUi.sourceFamily')):category==='birthday'?t('birthdayUi.title'):t(`calendarUi.${labelKeys[category]||'sourceCalendar'}`);
 return {
  id:sourceIdentity(event),sourceId:source?.id||null,category,
  name:source?.name||event?.payload?.provider||fallbackLabel,
  color:appearance.color||base.color,icon:appearance.icon||base.icon,
  configurable:Boolean(source?.id),source,
 };
}

export function memberDescriptor(event,family){
 const memberId=event?.payload?.member_id;
 if(!memberId)return null;
 const membership=(family?.memberships||[]).find(item=>String(item.id)===String(memberId)||String(item.user)===String(memberId));
 if(!membership)return null;
 return {id:membership.id,name:membership.display_name||membership.user_name||membership.username||membership.name||'Familienmitglied'};
}
