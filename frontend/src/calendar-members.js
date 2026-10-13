export const DEFAULT_CALENDAR_COLORS=['#2F855A','#2563EB','#7C3AED','#DB2777','#C2410C','#0F766E','#B91C1C','#4F46E5'];

export function membershipDisplayName(member){
 if(!member)return '';
 return member.display_name||member.username||member.user_name||member.name||'';
}

export function membershipCalendarColor(member){
 return member?.calendar_color||DEFAULT_CALENDAR_COLORS[0];
}

export function eventMemberDescriptor(event,family){
 const memberId=event?.payload?.member_id;
 if(!memberId)return null;
 const member=(family?.memberships||[]).find(item=>String(item.id)===String(memberId));
 if(!member)return null;
 const name=membershipDisplayName(member);
 return name?{id:member.id,name,color:membershipCalendarColor(member)}:null;
}

export function eventMemberStyle(event,family){
 const member=eventMemberDescriptor(event,family);
 if(!member||event?.source||event?.type!=='calendar.event')return {};
 return {'--calendar-member-color':member.color};
}
