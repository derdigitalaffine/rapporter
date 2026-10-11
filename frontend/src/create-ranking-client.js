import {api,AUTH_CHANGED_EVENT} from './api';
import {normalizeCreateRankingProfile} from './create-actions';

export const CREATE_RANKING_UPDATED_EVENT='famuhle:create-ranking-updated';
const CACHE_PREFIX='famuhle-create-ranking:';
const QUEUE_PREFIX='famuhle-create-usage:';
const MAX_QUEUE=100;

let activeUserId=null;
let identityRevision=0;
const flushes=new Map();

// A verified session establishes identity. Never recover identity from cached data.
export function setCreateRankingIdentity(userId){
  const next=userId==null?null:String(userId);
  if(next===activeUserId)return;
  activeUserId=next;identityRevision+=1;
  // Family-only v1 data has no owner and must never be adopted by a user.
  try{for(const key of Object.keys(localStorage)){
    if((key.startsWith(CACHE_PREFIX)||key.startsWith(QUEUE_PREFIX))&&!key.includes(':v2:'))localStorage.removeItem(key);
    if(!next&&(key.startsWith(CACHE_PREFIX)||key.startsWith(QUEUE_PREFIX)))localStorage.removeItem(key);
  }}catch{}
}
window.addEventListener(AUTH_CHANGED_EVENT,event=>{if(!event.detail?.authenticated)setCreateRankingIdentity(null)});
export function createRankingScope(family,userId){
  const member=family?.memberships?.find(row=>String(row.user)===String(userId));
  return userId!=null&&family?.id&&member?.id?{userId:String(userId),membershipId:String(member.id),familyId:String(family.id)}:null;
}
export function createRankingScopeKey(scope){return scope?JSON.stringify([scope.userId,scope.membershipId,scope.familyId]):''}
function current(scope,revision=identityRevision){return Boolean(scope&&String(scope.userId)===activeUserId&&revision===identityRevision)}
function cacheKey(scope){return `${CACHE_PREFIX}v2:${createRankingScopeKey(scope)}`}
function queueKey(scope){return `${QUEUE_PREFIX}v2:${createRankingScopeKey(scope)}`}
function readJson(key,fallback){try{return JSON.parse(localStorage.getItem(key)||'null')??fallback}catch{return fallback}}
function emit(scope,profile){window.dispatchEvent(new CustomEvent(CREATE_RANKING_UPDATED_EVENT,{detail:{scopeKey:createRankingScopeKey(scope),profile}}))}
function clearScope(scope){try{localStorage.removeItem(cacheKey(scope));localStorage.removeItem(queueKey(scope))}catch{};emit(scope,normalizeCreateRankingProfile({}))}
function saveProfile(scope,profile,revision=identityRevision){
  const normalized=normalizeCreateRankingProfile(profile);
  if(!current(scope,revision))return null;
  try{localStorage.setItem(cacheKey(scope),JSON.stringify(normalized))}catch{}
  emit(scope,normalized);return normalized;
}
export function loadCachedCreateRanking(scope){return current(scope)?normalizeCreateRankingProfile(readJson(cacheKey(scope),{})):normalizeCreateRankingProfile({})}
async function rankingRequest(scope,options,revision){
  if(!current(scope,revision))return null;
  try{
    const profile=await api(`/create-actions/?family=${encodeURIComponent(scope.familyId)}`,{...options,headers:{...options?.headers,'X-Create-Membership':scope.membershipId}});
    return saveProfile(scope,profile,revision);
  }catch(error){
    if(current(scope,revision)&&[401,403,404].includes(error?.status))clearScope(scope);
    throw error;
  }
}
export function fetchCreateRanking(scope){return rankingRequest(scope,{},identityRevision)}
export function patchCreateRanking(scope,patch){
  if(patch.reset_learning&&current(scope))try{localStorage.removeItem(queueKey(scope))}catch{}
  return rankingRequest(scope,{method:'PATCH',body:JSON.stringify(patch)},identityRevision);
}
function eventId(){
  if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
  const bytes=new Uint8Array(16);
  if(globalThis.crypto?.getRandomValues)globalThis.crypto.getRandomValues(bytes);else for(let index=0;index<bytes.length;index+=1)bytes[index]=Math.floor(Math.random()*256);
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(value=>value.toString(16).padStart(2,'0'));
  return `${hex.slice(0,4).join('')}-${hex.slice(4,6).join('')}-${hex.slice(6,8).join('')}-${hex.slice(8,10).join('')}-${hex.slice(10).join('')}`;
}
function queue(scope,payload){
  const rows=readJson(queueKey(scope),[]);
  const next=[...rows.filter(row=>row?.event_id!==payload.event_id),payload].slice(-MAX_QUEUE);
  try{localStorage.setItem(queueKey(scope),JSON.stringify(next))}catch{}
}
function optimisticProfile(scope,payload){
  const profile=loadCachedCreateRanking(scope);
  const rows=[...profile.stats];
  const index=rows.findIndex(row=>row.action_id===payload.action_id);
  const current=index>=0?rows[index]:{action_id:payload.action_id,use_count:0,last_used_at:null,context_stats:{},time_bucket_stats:{}};
  const context=payload.context_bucket||payload.origin_page||'';
  const next={...current,use_count:(Number(current.use_count)||0)+1,last_used_at:new Date().toISOString(),context_stats:{...(current.context_stats||{})}};
  if(context)next.context_stats[context]=(Number(next.context_stats[context])||0)+1;
  if(index>=0)rows[index]=next;else rows.push(next);
  return saveProfile(scope,{...profile,stats:rows});
}
function transient(error){return !error?.status||error.status>=500||error.status===408||error.status===429}
export async function recordCreateUsage({scope,actionId,originPage='',contextBucket=''}){
  const revision=identityRevision;
  if(!current(scope,revision)||!actionId)return null;
  const payload={event_id:eventId(),action_id:actionId,origin_page:originPage||'',context_bucket:contextBucket||'',success:true};
  optimisticProfile(scope,payload);
  try{return await rankingRequest(scope,{method:'POST',body:JSON.stringify(payload)},revision)}
  catch(error){if(current(scope,revision)&&transient(error))queue(scope,payload);throw error}
}
export function flushCreateUsageQueue(scope){
  if(!current(scope))return Promise.resolve();
  const key=queueKey(scope);
  if(flushes.has(key))return flushes.get(key);
  const pending=flushQueue(scope,identityRevision).finally(()=>flushes.delete(key));
  flushes.set(key,pending);return pending;
}
async function flushQueue(scope,revision){
  const rows=readJson(queueKey(scope),[]);
  if(!Array.isArray(rows))return;
  for(const payload of rows){
    if(!current(scope,revision))return;
    try{await rankingRequest(scope,{method:'POST',body:JSON.stringify(payload)},revision)}
    catch(error){if(transient(error)||[401,403,404].includes(error?.status))return}
    if(!current(scope,revision))return;
    // Remove only this receipt, preserving signals queued while replay was running.
    const remaining=readJson(queueKey(scope),[]).filter(row=>row.event_id!==payload.event_id);
    try{if(remaining.length)localStorage.setItem(queueKey(scope),JSON.stringify(remaining));else localStorage.removeItem(queueKey(scope))}catch{}
  }
}
