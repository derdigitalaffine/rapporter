import {useEffect,useState} from 'react';
import {Icon} from './icons';
import AvatarSymbol from './AvatarSymbol';
import './member-avatar.css';

function initials(person){
 const label=(person?.display_name||person?.username||'').trim();
 if(!label)return'';
 const parts=label.split(/\s+/).filter(Boolean);
 return (parts.length>1?`${parts[0][0]}${parts.at(-1)[0]}`:parts[0][0]).toUpperCase();
}

function foregroundFor(hex){
 const match=/^#([0-9a-f]{6})$/i.exec(hex||'');
 if(!match)return'#fff';
 const rgb=[0,2,4].map(offset=>parseInt(match[1].slice(offset,offset+2),16)/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);
 const luminance=.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];
 const black=(luminance+.05)/.05;
 const white=1.05/(luminance+.05);
 return black>=white?'#111':'#fff';
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
 const style={'--avatar-size':`${size}px`,...(tone?{'--member-avatar-color':tone,'--member-avatar-fg':foregroundFor(tone)}:{})};
 return <span className={`member-avatar-ui mode-${showPhoto?'photo':showIcon?'icon':'initials'} ${tone?'has-member-color':''} ${className}`} style={style} aria-label={decorative?undefined:label} aria-hidden={decorative?'true':undefined}>
  {showPhoto?<img src={src} alt={decorative?'':label} width={size} height={size} loading="lazy" onError={()=>setFailed(true)}/>:showIcon?<AvatarSymbol name={person.avatar_icon_key} size={Math.round(size*.42)}/>:fallback?<span aria-hidden="true">{fallback}</span>:<Icon name="user" size={Math.round(size*.42)}/>} 
 </span>;
}
