import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import {fetchCalendarEvents} from './calendar-events-api';
import {zonedDateKey} from './calendar-event-ui';
import {clearProjection,watchProjection} from './todayProjectionLifecycle';

const stores=new Map();
const unwrap=value=>Array.isArray(value)?value:(value?.actions||value?.results||[]);

export function nextCivilDateKey(timeZone='UTC',now=new Date()){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const read=type=>Number(parts.find(part=>part.type===type)?.value||0);
 const next=new Date(Date.UTC(read('year'),read('month')-1,read('day')+1,12));
 return `${next.getUTCFullYear()}-${String(next.getUTCMonth()+1).padStart(2,'0')}-${String(next.getUTCDate()).padStart(2,'0')}`;
}

function storeFor(familyId,timeZone='UTC'){
 const key=`${String(familyId||'')}|${timeZone}`;
 if(!stores.has(key))stores.set(key,{actions:[],events:[],loading:false,loaded:false,actionFailed:false,calendarFailed:false,day:'',generation:0,promise:null,listeners:new Set()});
 return stores.get(key);
}
function snapshot(store){return {actions:store.actions,events:store.events,loading:store.loading,loaded:store.loaded,actionFailed:store.actionFailed,calendarFailed:store.calendarFailed,day:store.day}}
function emit(store){const value=snapshot(store);store.listeners.forEach(listener=>listener(value))}

async function loadTomorrowData(family,{force=false}={}){
 const familyId=String(family?.id||'');
 if(!familyId)return {actions:[],events:[],loading:false,loaded:false,actionFailed:false,calendarFailed:false,day:''};
 const timeZone=family?.timezone||'UTC';
 const day=nextCivilDateKey(timeZone);
 const store=storeFor(familyId,timeZone);
 if(store.loading&&store.promise&&store.day===day)return store.promise;
 if(!force&&store.day===day){
  if(store.loaded)return snapshot(store);
 }
 if(force||store.day!==day)clearProjection(store,emit);
 const generation=store.generation+1;
 store.generation=generation;store.day=day;store.loading=true;store.actionFailed=false;store.calendarFailed=false;emit(store);
 const actionRequest=api(`/actions/?family=${encodeURIComponent(familyId)}&scope=upcoming`);
 const calendarRequest=fetchCalendarEvents({familyId,start:day,end:day});
 const promise=Promise.allSettled([actionRequest,calendarRequest]).then(([actionsResult,eventsResult])=>{
  if(store.generation!==generation)return snapshot(store);
  if(actionsResult.status==='fulfilled'){
   store.actions=unwrap(actionsResult.value).filter(item=>{
    if(String(item?.family||familyId)!==familyId)return false;
    const value=item?.due_at||item?.next_due_at;
    return Boolean(value&&zonedDateKey(value,timeZone)===day);
   });
   store.actionFailed=false;
  }else{store.actions=[];store.actionFailed=true}
  if(eventsResult.status==='fulfilled'){
   store.events=unwrap(eventsResult.value).filter(event=>String(event?.family||familyId)===familyId);
   store.calendarFailed=false;
  }else{store.events=[];store.calendarFailed=true}
  store.loading=false;store.loaded=true;store.promise=null;emit(store);return snapshot(store);
 });
 store.promise=promise;
 return promise;
}

export function useTomorrowData(family){
 const familyId=String(family?.id||'');
 const timeZone=family?.timezone||'UTC';
 const key=`${familyId}|${timeZone}`;
 const [view,setView]=useState(()=>({key,state:snapshot(storeFor(familyId,timeZone))}));
 const state=view.key===key?view.state:snapshot(storeFor(familyId,timeZone));
 useEffect(()=>{
  const store=storeFor(familyId,timeZone);let active=true;
  const listener=value=>{if(active)setView({key,state:value})};
  store.listeners.add(listener);setView({key,state:snapshot(store)});loadTomorrowData(family);
  watchProjection(store,{load:options=>loadTomorrowData(family,options),clear:()=>clearProjection(store,emit)});
  return()=>{active=false;store.listeners.delete(listener);if(!store.listeners.size)store.stopWatching?.()};
 },[key]);
 const refresh=useCallback(()=>loadTomorrowData(family,{force:true}),[key]);
 return {...state,refresh};
}
