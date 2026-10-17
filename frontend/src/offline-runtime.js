import {getSyncEngine,stopSyncAccount,SYNC_CHANGED} from './offline-sync-engine.js';
import {requestBackgroundSync} from './offline-recovery.js';
import {ensureLiveCoordinator,stopLiveAccount} from './offline-live.js';
const ACCOUNT='familyos-offline-account';
const PREFIX='familyos-offline-bootstrap:';
let transport=null;
let generation=0;
const enabled=new Set();
const meta=()=>{try{return JSON.parse(localStorage.getItem(PREFIX+localStorage.getItem(ACCOUNT))||'null')}catch{return null}};
export function offlineIdentity(){const data=meta();return data?.session?.offline_sync_protocol===1?data:null}
export function offlineEngine(familyId){const data=offlineIdentity();if(!data||!familyId)return null;return getSyncEngine({accountId:String(data.session.user.id),familyId:String(familyId),transport})}
export function setSyncTransport(fn){transport=fn}
function enableLive(e,familyId){const data=offlineIdentity();if(data&&e)ensureLiveCoordinator(e,{accountId:String(data.session.user.id),familyId:String(familyId)})}
export async function rememberOfflineBootstrap(path,data){
 if(path==='/families/'&&Array.isArray(data?.results))data=data.results;
 if(path==='/auth/session/'&&data?.offline_sync_protocol===1&&data.user?.id&&!data.user.is_superadmin){
  const accountId=String(data.user.id),old=localStorage.getItem(ACCOUNT);
  if(old&&old!==accountId)await clearOfflineIdentity();
  localStorage.setItem(ACCOUNT,accountId);
  const previous=meta()||{};
  const safeSession={authenticated:true,offline_sync_protocol:1,user:{id:data.user.id,username:data.user.username,is_superadmin:false}};
  localStorage.setItem(PREFIX+accountId,JSON.stringify({...previous,session:safeSession}));
  navigator.storage?.persist?.().catch(()=>{});
 }
 if(path.startsWith('/dashboard/')&&offlineIdentity()){const accountId=localStorage.getItem(ACCOUNT),familyId=new URL(path,'https://local.invalid').searchParams.get('family');const value={...data};for(const key of ['tasks','task_lists','events','shopping_lists'])delete value[key];const saved=meta();localStorage.setItem(PREFIX+accountId,JSON.stringify({...saved,dashboards:{...saved.dashboards,[familyId]:value}}))}
 if(path==='/families/'&&Array.isArray(data)&&offlineIdentity()){
  const accountId=localStorage.getItem(ACCOUNT);localStorage.setItem(PREFIX+accountId,JSON.stringify({...meta(),families:data}));
  for(const family of data){const e=offlineEngine(family.id);if(e)e.sync().then(()=>{enabled.add(String(family.id));enableLive(e,family.id)}).catch(()=>{})}
 }
}
export async function clearOfflineIdentity(){
 const old=localStorage.getItem(ACCOUNT);generation++;
 localStorage.removeItem(ACCOUNT);enabled.clear();
 if(old){stopLiveAccount(old);await stopSyncAccount(old);localStorage.removeItem(PREFIX+old)}
 // The old fallback database is not account-scoped. Explicit logout must erase
 // its private data too. Aborted/deferred legacy transactions are stopped by UI.
 await new Promise((resolve,reject)=>{const request=indexedDB.deleteDatabase('famuhle-offline-v1');request.onsuccess=resolve;request.onerror=()=>reject(request.error);request.onblocked=()=>reject(new Error('legacy_offline_cleanup_blocked'))});
}
export async function clearRemoteOfflineAccount(accountId){
 generation++;enabled.clear();stopLiveAccount(String(accountId));await stopSyncAccount(String(accountId));localStorage.removeItem(PREFIX+accountId);
}
export function offlineMetadata(path){
 const data=offlineIdentity();if(!data)return {handled:false};
 if(path==='/auth/session/')return {handled:true,value:data.session};
 if(path==='/families/'&&data.families)return {handled:true,value:data.families};
 return {handled:false};
}
export async function readyOfflineEngine(familyId){
 const e=offlineEngine(familyId);if(!e)return null;
 if(await e.ready()){enabled.add(String(familyId));enableLive(e,familyId);return e}
 await e.sync();if(!await e.ready())throw new Error('offline_prefetch_required');enabled.add(String(familyId));enableLive(e,familyId);return e;
}
export async function offlineShoppingRequest(path,options={}){
 const identity=offlineIdentity();if(!identity)return {handled:false};
 const url=new URL(path,'https://local.invalid'),route=url.pathname,method=(options.method||'GET').toUpperCase();
 if(!/^\/(shopping-lists|shopping-items|smart\/shopping(?:-lists)?\/)/.test(route))return {handled:false};
 let data={};if(options.body){try{data=JSON.parse(options.body)}catch{return {handled:false}}}
 const familyId=String(data.family||url.searchParams.get('family')||localStorage.getItem('famuhle-active-family')||identity.families?.[0]?.id||'');
 const revision=generation,e=await readyOfflineEngine(familyId);if(!e||revision!==generation)throw new Error('offline_scope_changed');
 const lists=async()=>{
  const items=await e.list('shopping_item');
  return (await e.list('shopping_list')).map(list=>{const children=items.filter(i=>i.shopping_list===list.id).sort((a,b)=>(a.position||0)-(b.position||0)||String(a.created_at||'').localeCompare(String(b.created_at||'')));return {...list,items:children,open_count:children.filter(i=>!i.checked).length,checked_count:children.filter(i=>i.checked).length}});
 };
 const match=route.match(/^\/(shopping-lists|shopping-items)\/(?:([^/]+)\/)?$/);
 if(match){
  const kind=match[1]==='shopping-lists'?'shopping_list':'shopping_item',id=match[2];
  if(id==='suggestions')return {handled:true,value:[]};
  if(method==='GET')return {handled:true,value:kind==='shopping_list'?(id?(await lists()).find(r=>r.id===id):await lists()):id?await e.get(kind,id):await e.list(kind)};
  if(['POST','PATCH','PUT','DELETE'].includes(method)){
   if(kind==='shopping_item')delete data.family;
   if(method==='POST'&&kind==='shopping_list')Object.assign(data,{family:familyId});
   const value=await e.mutate(kind,id,method==='POST'?'create':method==='DELETE'?'delete':'update',data);
   return {handled:true,value};
  }
 }
 if(route==='/smart/shopping/quick-add/'&&method==='POST')return {handled:true,value:await addShoppingLocally(familyId,data)};
 const clear=route.match(/^\/smart\/shopping-lists\/([^/]+)\/clear-checked\/$/);
 if(clear&&method==='POST'){const rows=(await e.list('shopping_item')).filter(r=>r.shopping_list===clear[1]&&r.checked);for(const row of rows)await e.mutate('shopping_item',row.id,'delete');return {handled:true,value:{deleted:rows.length}}}
 const reorder=route.match(/^\/smart\/shopping-lists\/([^/]+)\/reorder\/$/);
 if(reorder&&method==='POST'){const ids=data.item_ids||[],rows=(await e.list('shopping_item')).filter(r=>r.shopping_list===reorder[1]);if(ids.length!==new Set(ids).size||ids.some(id=>!rows.some(r=>r.id===id)))throw new Error('invalid_shopping_order');for(let i=0;i<ids.length;i++)await e.mutate('shopping_item',ids[i],'update',{position:i*1024});return {handled:true,value:{ok:true}}}
 return {handled:false};
}
const syncAll=()=>{const identity=offlineIdentity();for(const family of identity?.families||[])offlineEngine(family.id)?.sync().catch(()=>{})};
if(typeof window!=='undefined'){
 window.addEventListener('online',syncAll);
 window.addEventListener('storage',event=>{if(event.key===ACCOUNT&&event.oldValue&&event.oldValue!==event.newValue)clearRemoteOfflineAccount(event.oldValue).then(()=>globalThis.location?.reload?.()).catch(()=>globalThis.location?.reload?.())});
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')syncAll()});
 window.addEventListener('familyos:sync-now',syncAll);
 window.addEventListener(SYNC_CHANGED,event=>{if(offlineIdentity()&&['offline','retry'].includes(event.detail?.state))requestBackgroundSync()});
 navigator.serviceWorker?.addEventListener?.('message',event=>{if(event.data?.type==='FAMILYOS_SYNC_WAKE')syncAll()});
}

export async function offlineDashboard(path){
 if(!path.startsWith('/dashboard/'))return {handled:false};
 const saved=offlineIdentity();if(!saved)return {handled:false};
 const familyId=new URL(path,'https://local.invalid').searchParams.get('family'),e=offlineEngine(familyId);
 if(!e||!await e.ready())return {handled:false};
 const items=await e.list('shopping_item'),lists=await e.list('shopping_list');
 return {handled:true,value:{...(saved.dashboards?.[familyId]||{}),tasks:await e.list('task'),task_lists:await e.list('task_list'),events:await e.list('event'),shopping_lists:lists.map(list=>({...list,items:items.filter(item=>item.shopping_list===list.id)})),routines:saved.dashboards?.[familyId]?.routines||[],offline_fallback:true}};
}

export async function addShoppingLocally(familyId,payload){
 const e=await readyOfflineEngine(familyId),name=String(payload.name||'').trim();if(!name)throw new Error('item_name_required');
 const listId=payload.shopping_list||(await e.list('shopping_list')).find(l=>!l.archived)?.id;if(!listId)throw new Error('shopping_list_required');
 const values={};for(const key of ['quantity','category','aisle','note'])if(payload[key]!==undefined&&payload[key]!==null&&payload[key]!=='')values[key]=payload[key];if('favorite' in payload)values.favorite=Boolean(payload.favorite);
 const item=await e.mutate('shopping_item',undefined,'create',{shopping_list:listId,name,...values,checked:false});
 return {item,reused:false};
}
