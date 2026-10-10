import {useEffect} from 'react';

const SESSION_MARKER='famuhle-session';
const BADGE_MESSAGE='FAMILYOS_BADGE';

function signedIn(){return localStorage.getItem(SESSION_MARKER)==='1'}
async function clearNativeBadge(){try{if(navigator.clearAppBadge)await navigator.clearAppBadge()}catch{}}
async function setNativeBadge(count){const value=Math.max(0,Number(count)||0);try{if(value>0&&navigator.setAppBadge)await navigator.setAppBadge(value);else if(value===0&&navigator.clearAppBadge)await navigator.clearAppBadge()}catch{}}
async function acknowledge(){
 if(!signedIn()){await clearNativeBadge();return}
 await clearNativeBadge();
 try{await fetch('/api/push/badge/',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'}})}catch{}
}

export default function PwaBadgeManager(){
 useEffect(()=>{
  const onVisible=()=>{if(document.visibilityState==='visible')acknowledge()};
  const onFocus=()=>acknowledge();
  const onOnline=()=>{if(document.visibilityState==='visible')acknowledge()};
  const onMessage=event=>{if(event.data?.type!==BADGE_MESSAGE)return;if(document.visibilityState==='visible')acknowledge();else setNativeBadge(event.data.count)};
  onVisible();
  document.addEventListener('visibilitychange',onVisible);
  window.addEventListener('focus',onFocus);
  window.addEventListener('online',onOnline);
  navigator.serviceWorker?.addEventListener('message',onMessage);
  return()=>{document.removeEventListener('visibilitychange',onVisible);window.removeEventListener('focus',onFocus);window.removeEventListener('online',onOnline);navigator.serviceWorker?.removeEventListener('message',onMessage)};
 },[]);
 return null;
}
