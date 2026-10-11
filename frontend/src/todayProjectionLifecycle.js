import {AUTH_CHANGED_EVENT,isAuthenticated} from './api';

// Lifecycle only: both projections still use the canonical Action/Calendar APIs.
export function clearProjection(store,emit){
 store.generation+=1;store.actions=[];store.events=[];store.loaded=false;store.loading=false;store.promise=null;store.day='';store.actionFailed=false;store.calendarFailed=false;emit(store);
}
export function watchProjection(store,{load,clear}){
 if(store.stopWatching)return;
 const refresh=()=>{if(isAuthenticated())load({force:true})};
 const auth=()=>{clear();if(isAuthenticated())load()};
 const visible=()=>{if(document.visibilityState==='visible')refresh()};
 window.addEventListener(AUTH_CHANGED_EVENT,auth);
 window.addEventListener('focus',refresh);
 document.addEventListener('visibilitychange',visible);
 // One timer per shared store, including DST/civil-day rollover and ACL revalidation.
 const timer=setInterval(()=>{if(document.visibilityState==='visible')refresh()},60_000);
 store.stopWatching=()=>{clearInterval(timer);window.removeEventListener(AUTH_CHANGED_EVENT,auth);window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',visible);store.stopWatching=null;clear()};
}
