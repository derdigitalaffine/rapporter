export const DEFAULT_CALENDAR_COLORS=['#2F855A','#2563EB','#7C3AED','#DB2777','#C2410C','#0F766E','#B91C1C','#4F46E5'];

export function membershipDisplayName(member){
 if(!member)return '';
 return member.display_name||member.username||member.user_name||member.name||'';
}

export function membershipCalendarColor(member){
 return member?.calendar_color||DEFAULT_CALENDAR_COLORS[0];
}

export function eventParticipantIds(event){
 const participantValues=Array.isArray(event?.participants)?event.participants:[];
 const ids=participantValues.map(value=>typeof value==='object'?value?.id:value).filter(Boolean).map(String);
 if(ids.length)return [...new Set(ids)];
 const legacy=event?.payload?.member_id;
 return legacy?[String(legacy)]:[];
}

export function eventMemberDescriptors(event,family){
 const byId=new Map((family?.memberships||[]).map(member=>[String(member.id),member]));
 return eventParticipantIds(event).map(id=>{
  const member=byId.get(String(id));
  if(!member)return null;
  const name=membershipDisplayName(member);
  return name?{id:member.id,name,color:membershipCalendarColor(member),member}:null;
 }).filter(Boolean);
}

export function eventMemberDescriptor(event,family){
 return eventMemberDescriptors(event,family)[0]||null;
}

export function eventMemberStyle(event,family){
 const members=eventMemberDescriptors(event,family);
 if(members.length!==1||event?.source||event?.type!=='calendar.event')return {};
 return {'--calendar-member-color':members[0].color};
}
