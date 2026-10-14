import {useEffect,useState} from 'react';
import {Icon} from './icons';
import './member-avatar.css';

function initials(person){
 const label=(person?.display_name||person?.username||'').trim();
 if(!label)return'';
 const parts=label.split(/\s+/).filter(Boolean);
 return (parts.length>1?`${parts[0][0]}${parts.at(-1)[0]}`:parts[0][0]).toUpperCase();
}

export default function MemberAvatar({person,size=44,className='',decorative=false,color=null}){
 const src=person?.avatar_url||person?.avatar||'';
 const mode=person?.avatar_mode||(src?'photo':person?.avatar_icon_key?'icon':'initials');
 const tone=color||person?.avatar_color||person?.calendar_color||null;
 const [failed,setFailed]=useState(false);
 useEffect(()=>setFailed(false),[src]);
 const label=person?.display_name||person?.username||'Person';
 const fallback=initials(person);
 const showPhoto=mode==='photo'&&src&&!failed;
 const showIcon=mode==='icon'&&person?.avatar_icon_key;
 const style={'--avatar-size':`${size}px`,...(tone?{'--member-avatar-color':tone}:{})};
 return <span className={`member-avatar-ui mode-${showPhoto?'photo':showIcon?'icon':'initials'} ${tone?'has-member-color':''} ${className}`} style={style} aria-label={decorative?undefined:label} aria-hidden={decorative?'true':undefined}>
  {showPhoto?<img src={src} alt={decorative?'':label} width={size} height={size} loading="lazy" onError={()=>setFailed(true)}/>:showIcon?<Icon name={person.avatar_icon_key} size={Math.round(size*.42)}/>:fallback?<span aria-hidden="true">{fallback}</span>:<Icon name="user" size={Math.round(size*.42)}/>} 
 </span>;
}
