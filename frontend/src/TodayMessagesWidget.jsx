import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';

function relativeTime(value,language){
 if(!value)return '';
 const delta=new Date(value).getTime()-Date.now();
 const abs=Math.abs(delta);
 const locale=language?.startsWith('de')?'de':'en';
 const rtf=new Intl.RelativeTimeFormat(locale,{numeric:'auto'});
 if(abs<3600000)return rtf.format(Math.round(delta/60000),'minute');
 if(abs<86400000)return rtf.format(Math.round(delta/3600000),'hour');
 return rtf.format(Math.round(delta/86400000),'day');
}

export default function TodayMessagesWidget({family,open,language}){
 const de=language?.startsWith('de');
 const [rows,setRows]=useState([]);
 useEffect(()=>{
  let active=true;
  setRows([]);
  api('/chat/conversations/').then(response=>{
   if(!active)return;
   const familyRows=(response?.results||[])
    .filter(row=>String(row.family_id||'')===String(family.id)&&['family','system'].includes(row.channel))
    .sort((a,b)=>Number(b.unread||0)-Number(a.unread||0)||String(a.channel).localeCompare(String(b.channel)))
    .slice(0,2);
   setRows(familyRows);
  }).catch(()=>{if(active)setRows([])});
  return()=>{active=false};
 },[family.id]);
 const unread=rows.reduce((sum,row)=>sum+Number(row.unread||0),0);
 const openChat=row=>window.location.assign(`/?page=inbox&chat=${encodeURIComponent(row.id)}`);
 return <section className="today-section today-inbox today-messages" data-testid="today-inbox">
  <div className="today-section-head"><div><h2>{de?'Nachrichten':'Messages'}</h2><small>{unread?`${unread} ${de?'ungelesen':'unread'}`:(de?'Alles gelesen':'All caught up')}</small></div><button className="today-link" onClick={()=>open('inbox')}>{de?'Alle':'All'} <Icon name="next"/></button></div>
  {rows.length?<div className="today-inbox-list">{rows.map(row=>{
   const hasUnread=Number(row.unread||0)>0;
   const last=row.last_message;
   const preview=last?.deleted?(de?'Nachricht gelöscht':'Message deleted'):(last?.body||(row.channel==='system'?(de?'Systemmeldungen':'System messages'):(de?'Familienchat':'Family chat')));
   return <button key={row.id} onClick={()=>openChat(row)}>
    <span className={`today-inbox-icon ${hasUnread?'unread':''}`}><Icon name={row.channel==='system'?'inbox':'members'}/></span>
    <span className="grow"><strong>{row.title}</strong><small>{[preview,last?.created_at&&relativeTime(last.created_at,language)].filter(Boolean).join(' · ')}</small></span>
    {hasUnread&&<i aria-label={de?'Ungelesen':'Unread'}/>}<Icon name="next"/>
   </button>
  })}</div>:<button className="today-calm today-inbox-empty" onClick={()=>open('inbox')}><Icon name="inbox"/><strong>{de?'Nachrichten öffnen':'Open messages'}</strong><span>{de?'Familie und System an einem Ort':'Family and system in one place'}</span></button>}
 </section>;
}
