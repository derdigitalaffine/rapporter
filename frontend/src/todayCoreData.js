import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import {fetchCalendarEvents} from './calendar-events-api';
import {zonedDateKey} from './calendar-event-ui';

const stores=new Map();
const unwrap=value=>Array.isArray(value)?value:(value?.actions||value?.results||[]);

function storeFor(familyId){
 const key=String(familyId||'');
 if(!stores.has(key))stores.set(key,{actions:[],events:[],loading:false,loaded:false,actionFailed:false,calendarFailed:false,day:'',generation:0,promise:null,listeners:new Set()});
 return stores.get(key);
}
function snapshot(store){return {actions:store.actions,events:store.events,loading:store.loading,loaded:store.loaded,actionFailed:store.actionFailed,calendarFailed:store.calendarFailed}}
function emit(store){const value=snapshot(store);store.listeners.forEach(listener=>listener(value))}

async function loadTodayCoreData(family,{force=false}={}){
 const familyId=String(family?.id||'');
 if(!familyId)return {actions:[],events:[],loading:false,loaded:false,actionFailed:false,calendarFailed:false};
 const timeZone=family?.timezone||'UTC';
 const day=zonedDateKey(new Date(),timeZone);
 const store=storeFor(familyId);
 if(!force&&store.day===day){
  if(store.loading&&store.promise)return store.promise;
  if(store.loaded)return snapshot(store);
 }
 const generation=store.generation+1;
 store.generation=generation;store.day=day;store.loading=true;store.actionFailed=false;store.calendarFailed=false;emit(store);
 const actionRequest=api(`/actions/?family=${encodeURIComponent(familyId)}&scope=today`);
 const calendarRequest=fetchCalendarEvents({familyId,start:day,end:day});
 const promise=Promise.allSettled([actionRequest,calendarRequest]).then(([actionsResult,eventsResult])=>{
  if(store.generation!==generation)return snapshot(store);
  if(actionsResult.status==='fulfilled'){
   store.actions=unwrap(actionsResult.value).filter(item=>String(item?.family||familyId)===familyId);
   store.actionFailed=false;
  }else{
   store.actions=[];store.actionFailed=true;
  }
  if(eventsResult.status==='fulfilled'){
   store.events=unwrap(eventsResult.value).filter(event=>String(event?.family||familyId)===familyId);
   store.calendarFailed=false;
  }else{
   store.events=[];store.calendarFailed=true;
  }
  store.loading=false;store.loaded=true;store.promise=null;emit(store);return snapshot(store);
 });
 store.promise=promise;
 return promise;
}

export function useTodayCoreData(family){
 const familyId=String(family?.id||'');
 const timeZone=family?.timezone||'UTC';
 const [state,setState]=useState(()=>snapshot(storeFor(familyId)));
 useEffect(()=>{
  const store=storeFor(familyId);
  let active=true;
  const listener=value=>{if(active)setState(value)};
  store.listeners.add(listener);setState(snapshot(store));
  loadTodayCoreData(family);
  return()=>{active=false;store.listeners.delete(listener)};
 },[familyId,timeZone]);
 const refresh=useCallback(()=>loadTodayCoreData(family,{force:true}),[familyId,timeZone]);
 return {...state,refresh};
}

export function refreshTodayCoreData(family){return loadTodayCoreData(family,{force:true})}
