export function membershipDisplayName(member){
 if(!member)return '';
 return member.display_name||member.username||member.user_name||member.name||'';
}

export function eventMemberDescriptor(event,family){
 const memberId=event?.payload?.member_id;
 if(!memberId)return null;
 const member=(family?.memberships||[]).find(item=>String(item.id)===String(memberId));
 if(!member)return null;
 const name=membershipDisplayName(member);
 return name?{id:member.id,name}:null;
}
