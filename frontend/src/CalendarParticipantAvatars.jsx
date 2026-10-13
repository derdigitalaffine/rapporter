import MemberAvatar from './MemberAvatar';
import {eventMemberDescriptors} from './calendar-members';
import './calendar-participants.css';

export default function CalendarParticipantAvatars({event,family,max=3,size=22,className='',withNames=false}){
 const members=eventMemberDescriptors(event,family);
 if(!members.length)return null;
 const visible=members.slice(0,max);
 const hidden=Math.max(0,members.length-visible.length);
 const names=members.map(member=>member.name).join(', ');
 return <span className={`calendar-participants ${className}`} aria-label={`Personen: ${names}`} title={names}>
  <span className="calendar-participant-stack" aria-hidden="true">{visible.map(({id,color,member})=><MemberAvatar key={id} person={member} color={color} size={size} decorative/>)}{hidden>0&&<span className="calendar-participant-more" style={{'--participant-size':`${size}px`}}>+{hidden}</span>}</span>
  {withNames&&<span className="calendar-participant-names">{names}</span>}
 </span>;
}
