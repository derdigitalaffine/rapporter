import {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {api} from './api';
import {Icon} from './icons';
import './header-messenger-shortcut.css';

const unreadChats=rows=>(rows||[]).reduce((sum,row)=>sum+(Number(row?.unread)||0),0);

export default function HeaderMessengerShortcut(){
 const [mount,setMount]=useState(null);
 const [unread,setUnread]=useState(0);
 const [active,setActive]=useState(false);

 useEffect(()=>{
  let host=null;
  let live=true;
  const locate=()=>{
   const context=document.querySelector('.topbar-context');
   if(!context)return;
   if(!host){
    host=document.createElement('span');
    host.className='header-messenger-mount';
    const profile=context.querySelector('.profile-shortcut');
    context.insertBefore(host,profile||context.firstChild);
    setMount(host);
   }
   setActive(document.querySelector('main[data-page="inbox"]')!==null);
  };
  const refresh=async()=>{
   try{const payload=await api('/chat/conversations/');if(live)setUnread(unreadChats(payload?.results||payload||[]))}catch{/* Header messaging remains usable when unread refresh is unavailable. */}
  };
  locate();void refresh();
  const observer=new MutationObserver(locate);observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['data-page']});
  const visible=()=>{if(document.visibilityState==='visible')void refresh()};
  document.addEventListener('visibilitychange',visible);
  const timer=window.setInterval(refresh,30000);
  return()=>{live=false;observer.disconnect();document.removeEventListener('visibilitychange',visible);window.clearInterval(timer);host?.remove()};
 },[]);

 function openMessenger(){
  const state={...history.state,page:'inbox',appNavigation:true};
  history.pushState(state,'','/?page=inbox');
  window.dispatchEvent(new PopStateEvent('popstate',{state}));
  setActive(true);
 }

 if(!mount)return null;
 const label=unread>0?`Nachrichten, ${unread} ungelesen`:'Nachrichten';
 return createPortal(<button type="button" className={`header-messenger-button ${active?'active':''}`} onClick={openMessenger} aria-label={label} aria-current={active?'page':undefined} title="Nachrichten"><Icon name="inbox" size={20}/>{unread>0&&<span className="header-messenger-badge" aria-hidden="true">{unread>99?'99+':unread}</span>}</button>,mount);
}
