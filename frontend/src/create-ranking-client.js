import {api} from './api';
import {normalizeCreateRankingProfile} from './create-actions';

export const CREATE_RANKING_UPDATED_EVENT='famuhle:create-ranking-updated';
const CACHE_PREFIX='famuhle-create-ranking:';
const QUEUE_PREFIX='famuhle-create-usage:';
const MAX_QUEUE=100;

function cacheKey(familyId){return `${CACHE_PREFIX}${familyId}`}
function queueKey(familyId){return `${QUEUE_PREFIX}${familyId}`}
function readJson(key,fallback){
  try{return JSON.parse(localStorage.getItem(key)||'null')??fallback}catch{return fallback}
}
function emit(familyId,profile){window.dispatchEvent(new CustomEvent(CREATE_RANKING_UPDATED_EVENT,{detail:{familyId,profile}}))}
function saveProfile(familyId,profile){
  const normalized=normalizeCreateRankingProfile(profile);
  try{localStorage.setItem(cacheKey(familyId),JSON.stringify(normalized))}catch{}
  emit(familyId,normalized);
  return normalized;
}
export function loadCachedCreateRanking(familyId){return familyId?normalizeCreateRankingProfile(readJson(cacheKey(familyId),{})):normalizeCreateRankingProfile({})}
export async function fetchCreateRanking(familyId){
  const profile=await api(`/create-actions/?family=${encodeURIComponent(familyId)}`);
  return saveProfile(familyId,profile);
}
export async function patchCreateRanking(familyId,patch){
  const profile=await api(`/create-actions/?family=${encodeURIComponent(familyId)}`,{method:'PATCH',body:JSON.stringify(patch)});
  return saveProfile(familyId,profile);
}
function eventId(){
  if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
  const bytes=new Uint8Array(16);
  if(globalThis.crypto?.getRandomValues)globalThis.crypto.getRandomValues(bytes);else for(let index=0;index<bytes.length;index+=1)bytes[index]=Math.floor(Math.random()*256);
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(value=>value.toString(16).padStart(2,'0'));
  return `${hex.slice(0,4).join('')}-${hex.slice(4,6).join('')}-${hex.slice(6,8).join('')}-${hex.slice(8,10).join('')}-${hex.slice(10).join('')}`;
}
function queue(familyId,payload){
  const rows=readJson(queueKey(familyId),[]);
  const next=[...rows.filter(row=>row?.event_id!==payload.event_id),payload].slice(-MAX_QUEUE);
  try{localStorage.setItem(queueKey(familyId),JSON.stringify(next))}catch{}
}
function optimisticProfile(familyId,payload){
  const profile=loadCachedCreateRanking(familyId);
  const rows=[...profile.stats];
  const index=rows.findIndex(row=>row.action_id===payload.action_id);
  const current=index>=0?rows[index]:{action_id:payload.action_id,use_count:0,last_used_at:null,context_stats:{},time_bucket_stats:{}};
  const context=payload.context_bucket||payload.origin_page||'';
  const next={...current,use_count:(Number(current.use_count)||0)+1,last_used_at:new Date().toISOString(),context_stats:{...(current.context_stats||{})}};
  if(context)next.context_stats[context]=(Number(next.context_stats[context])||0)+1;
  if(index>=0)rows[index]=next;else rows.push(next);
  return saveProfile(familyId,{...profile,stats:rows});
}
function transient(error){return !error?.status||error.status>=500||error.status===408||error.status===429}
export async function recordCreateUsage({familyId,actionId,originPage='',contextBucket=''}){
  if(!familyId||!actionId)return null;
  const payload={event_id:eventId(),action_id:actionId,origin_page:originPage||'',context_bucket:contextBucket||'',success:true};
  optimisticProfile(familyId,payload);
  try{
    const profile=await api(`/create-actions/?family=${encodeURIComponent(familyId)}`,{method:'POST',body:JSON.stringify(payload)});
    return saveProfile(familyId,profile);
  }catch(error){
    if(transient(error))queue(familyId,payload);
    throw error;
  }
}
export async function flushCreateUsageQueue(familyId){
  if(!familyId)return;
  const rows=readJson(queueKey(familyId),[]);
  if(!rows.length)return;
  const keep=[];
  for(let index=0;index<rows.length;index+=1){
    const payload=rows[index];
    try{
      const profile=await api(`/create-actions/?family=${encodeURIComponent(familyId)}`,{method:'POST',body:JSON.stringify(payload)});
      saveProfile(familyId,profile);
    }catch(error){
      if(transient(error)){keep.push(...rows.slice(index));break}
    }
  }
  try{if(keep.length)localStorage.setItem(queueKey(familyId),JSON.stringify(keep));else localStorage.removeItem(queueKey(familyId))}catch{}
}
