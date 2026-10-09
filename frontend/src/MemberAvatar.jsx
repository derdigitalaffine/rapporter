import {useEffect,useState} from 'react';
import {Icon} from './icons';
import './member-avatar.css';

function initials(person){
 const label=(person?.display_name||person?.username||'').trim();
 if(!label)return'';
 const parts=label.split(/\s+/).filter(Boolean);
 return (parts.length>1?`${parts[0][0]}${parts.at(-1)[0]}`:parts[0].slice(0,2)).toUpperCase();
}

export default function MemberAvatar({person,size=44,className='',decorative=false}){
 const src=person?.avatar_url||person?.avatar||'';
 const [failed,setFailed]=useState(false);
 useEffect(()=>setFailed(false),[src]);
 const label=person?.display_name||person?.username||'Person';
 const fallback=initials(person);
 return <span className={`member-avatar-ui ${className}`} style={{'--avatar-size':`${size}px`}} aria-label={decorative?undefined:label} aria-hidden={decorative?'true':undefined}>
  {src&&!failed?<img src={src} alt={decorative?'':label} width={size} height={size} loading="lazy" onError={()=>setFailed(true)}/>:fallback?<span aria-hidden="true">{fallback}</span>:<Icon name="user" size={Math.round(size*.42)}/>} 
 </span>;
}
