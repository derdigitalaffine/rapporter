import {createLocalSyncStore,clearLocalSyncAccount} from './local-sync-store.js';
export const SYNC_CHANGED='familyos:sync-changed';
export const TYPE_STORES=Object.freeze({task_list:'taskLists',task:'tasks',shopping_list:'shoppingLists',shopping_item:'shoppingItems',event:'events'});
const SNAPSHOT_TYPES={task_lists:'task_list',tasks:'task',shopping_lists:'shopping_list',shopping_items:'shopping_item',events:'event'};
const engines=new Map(),locks=new Map();
const put=(store,value)=>({store,type:'put',value});
const remove=(store,id)=>({store,type:'delete',id});
const uuid=()=>crypto.randomUUID();
async function localLock(key,work){
 if(globalThis.navigator?.locks)return navigator.locks.request(`familyos-local:${key}`,work);
 const next=(locks.get(key)||Promise.resolve()).catch(()=>{}).then(work);locks.set(key,next);
 try{return await next}finally{if(locks.get(key)===next)locks.delete(key)}
}
function emit(engine){globalThis.window?.dispatchEvent(new CustomEvent(SYNC_CHANGED,{detail:{accountId:engine.accountId,familyId:engine.familyId,state:engine.state}}))}
function overlay(server,mutations){
 let data=server?structuredClone(server):null;
 for(const m of mutations){
  if(m.operation==='create')data={...m.data,id:m.entity_id,version:0};
  else if(m.operation==='update')data={...(data||{}),...m.changes,id:m.entity_id};
  else if(m.operation==='delete')data=null;
  else if(m.command==='complete_task'&&data)data={...data,completed_at:m.local_time};
  else if(m.command==='reopen_task'&&data)data={...data,completed_at:null};
  else if(m.command==='move_task'&&data)data={...data,workflow_column:m.args.column_id,completed_at:m.args.local_terminal?m.local_time:null};
 }
 return data;
}
const ordered=rows=>rows.sort((a,b)=>a.order-b.order||a.mutation_id.localeCompare(b.mutation_id));
function envelope(m){
 const result={mutation_id:m.mutation_id,entity_type:m.entity_type,entity_id:m.entity_id,operation:m.operation,base_version:m.base_version};
 for(const key of ['data','changes','command','args'])if(m[key]!==undefined)result[key]=m[key];
 return result;
}
export function getSyncEngine({accountId,familyId,transport}){
 const key=JSON.stringify([String(accountId),String(familyId)]);
 if(engines.has(key)){const e=engines.get(key);if(transport)e.transport=transport;return e}
 const e=new SyncEngine(String(accountId),String(familyId),transport,key);engines.set(key,e);return e;
}
export async function stopSyncAccount(accountId){
 const owned=[...engines.values()].filter(e=>e.accountId===String(accountId));
 for(const e of owned)e.stop();
 await Promise.all(owned.map(e=>e.inflight?.catch(()=>{})));
 for(const e of owned){await localLock(e.key,()=>e.store.write([]));engines.delete(e.key)}
 await clearLocalSyncAccount(String(accountId));
}
export class SyncEngine{
 constructor(accountId,familyId,transport,key=JSON.stringify([accountId,familyId])){
  Object.assign(this,{accountId,familyId,transport,key});this.store=createLocalSyncStore({accountId,familyId});
  this.state='idle';this.stopped=false;this.inflight=null;this.abort=new AbortController();
 }
 async ready(){return Boolean(await this.store.get('syncState','cursor'))}
 async list(kind){return (await this.store.list(TYPE_STORES[kind])).filter(r=>r.data&&!r.deleted).map(r=>({...r.data,_offlinePending:r.sync_status==='pending'}))}
 async get(kind,id){return (await this.list(kind)).find(r=>r.id===id)||null}
 async mutate(kind,id,operation,payload={}){
  if(this.stopped)throw new Error('sync_stopped');
  const name=TYPE_STORES[kind];if(!name)throw new Error('unsupported_sync_entity');id=id||uuid();
  return localLock(this.key,async()=>{
   if(this.stopped)throw new Error('sync_stopped');
   const old=await this.store.get(name,id);
   if(kind==='event'&&(old?.data?.read_only||old?.data?.source||payload.source))throw new Error('read_only_source');
   const all=ordered(await this.store.list('outbox')),pending=all.filter(m=>m.entity_type===kind&&m.entity_id===id),last=pending.at(-1);
   const safe=last&&last.state==='pending'&&!last.attempted&&['create','update'].includes(last.operation);
   const m={id:uuid(),entity_type:kind,entity_id:id,operation,base_version:old?.version||null,state:'pending',attempted:false,order:Math.max(0,...all.map(m=>m.order||0))+1,local_time:new Date().toISOString(),base_data:structuredClone(old?.data||{})};m.mutation_id=m.id;
   if(operation==='create')m.data=structuredClone(payload);
   else if(operation==='update')m.changes=structuredClone(payload);
   else if(operation==='command'){m.command=payload.command;m.args=payload.args||{}}
   else if(operation!=='delete')throw new Error('unsupported_sync_operation');
   let ops=[],next=pending;
   if(safe&&last.operation==='create'&&operation==='delete'&&pending.length===1)ops=[remove('outbox',last.id),remove(name,id)];
   else{
    if(safe&&operation==='update'){
     if(last.operation==='create')last.data={...last.data,...m.changes};else last.changes={...last.changes,...m.changes};ops.push(put('outbox',last));
    }else{next=[...pending,m];ops.push(put('outbox',m))}
    const server=old?.server_data??(old?.sync_status!=='pending'?old?.data:null),data=overlay(server,next);
    ops.push(put(name,{id,version:old?.version||0,data,server_data:server||null,sync_status:'pending',deleted:data===null}));
   }
   await this.store.write(ops);emit(this);this.schedule();return operation==='delete'?null:(await this.store.get(name,id))?.data;
  });
 }
 schedule(){if(!this.stopped){clearTimeout(this.timer);this.timer=setTimeout(()=>this.sync().catch(()=>{}),30)}}
 stop(){this.stopped=true;clearTimeout(this.timer);this.abort.abort();this.state='stopped'}
 sync(){if(this.stopped)return Promise.resolve();if(this.inflight)return this.inflight;this.inflight=this.run().finally(()=>{this.inflight=null});return this.inflight}
 async run(){
  if(globalThis.navigator?.onLine===false){this.state='offline';emit(this);return}
  if(!this.transport)throw new Error('sync_transport_missing');this.state='synchronizing';emit(this);
  try{
   const batch=await localLock(this.key,async()=>{
    const seen=new Set();
    const rows=ordered(await this.store.list('outbox')).filter(m=>{const key=`${m.entity_type}:${m.entity_id}`;if(seen.has(key))return false;seen.add(key);return true}).slice(0,100);
    await this.store.write(rows.map(m=>put('outbox',{...m,state:'sending',attempted:true})));
    return {rows,cursor:(await this.store.get('syncState','cursor'))?.cursor??null,calendar_projection_key:(await this.store.get('meta','projections'))?.data?.calendar_key??null};
   });
   const r=await this.transport({protocol_version:1,family_id:this.familyId,cursor:batch.cursor,calendar_projection_key:batch.calendar_projection_key,mutations:batch.rows.map(envelope)},this.abort.signal);
   if(this.stopped)return;
   if(r.protocol_version!==1||!['delta','snapshot'].includes(r.mode)||!Number.isSafeInteger(r.cursor))throw new Error('unsupported_sync_protocol');
   await localLock(this.key,()=>this.install(r,batch.rows));if(this.stopped)return;
   this.state=(await this.store.list('conflicts')).length?'action-required':'synced';emit(this);
   if((await this.store.list('outbox')).length)this.schedule();
  }catch(error){
   if(this.stopped)return;
   this.state=[401,403].includes(error.status)?'auth-required':globalThis.navigator?.onLine===false?'offline':'retry';emit(this);
   if(![401,403,409].includes(error.status)){clearTimeout(this.timer);this.timer=setTimeout(()=>this.sync().catch(()=>{}),10000)}throw error;
  }
 }
 async install(r,sent){
  const existing={};for(const [kind,name] of Object.entries(TYPE_STORES))existing[kind]=new Map((await this.store.list(name)).map(row=>[row.id,row]));
  const remaining=new Map(ordered(await this.store.list('outbox')).map(m=>[m.id,m])),ops=[];
  for(const result of r.mutation_results||[]){
   const m=sent.find(row=>row.mutation_id===result.mutation_id);if(!m)throw new Error('invalid_sync_acknowledgement');
   if(!['applied','already_applied','conflict','rejected'].includes(result.status))throw new Error('invalid_sync_result');
   remaining.delete(m.id);ops.push(remove('outbox',m.id));
   if(['conflict','rejected'].includes(result.status))ops.push(put('conflicts',{id:m.id,mutation:m,result,local_data:structuredClone(existing[m.entity_type].get(m.entity_id)?.data),created_at:Date.now()}));
   else for(const later of remaining.values())if(later.entity_type===m.entity_type&&later.entity_id===m.entity_id&&!later.attempted){
    const safe=m.operation==='create'&&!later.base_version || result.data&&later.operation==='update'&&Object.keys(later.changes).every(key=>JSON.stringify(later.base_data?.[key])===JSON.stringify(result.data[key]));
    if(safe){later.base_version=result.version;ops.push(put('outbox',later))}
   }
   if(result.data)existing[m.entity_type].set(m.entity_id,{id:m.entity_id,version:result.data.version,server_data:result.data});
   if(m.operation==='delete'&&['applied','already_applied'].includes(result.status))existing[m.entity_type].delete(m.entity_id);
  }
  // An omitted acknowledgement leaves the stable mutation queued for retry.
  if(r.mode==='snapshot'){
   for(const rows of Object.values(existing))for(const row of rows.values())row.server_data=null;
   for(const [key,items] of Object.entries(r.snapshot||{})){const kind=SNAPSHOT_TYPES[key];if(kind)for(const data of items)existing[kind].set(data.id,{id:data.id,version:data.version,data,server_data:data})}
  }else for(const change of r.changes||[]){
   const rows=existing[change.entity_type];if(!rows)continue;
   if(change.operation==='delete')rows.delete(change.entity_id);else rows.set(change.entity_id,{id:change.entity_id,version:change.version,server_data:change.data});
  }
  for(const [kind,name] of Object.entries(TYPE_STORES)){
   if(!Array.isArray(r.visibility?.[kind]))throw new Error('sync_visibility_missing');const allowed=new Set(r.visibility[kind]),rows=existing[kind];
   for(const m of remaining.values())if(m.entity_type===kind&&!rows.has(m.entity_id))rows.set(m.entity_id,{id:m.entity_id,version:0,server_data:null});
   const oldIds=new Set((await this.store.list(name)).map(row=>row.id));
   for(const [id,row] of rows){
    const queued=[...remaining.values()].filter(m=>m.entity_type===kind&&m.entity_id===id);let server=row.server_data??null;
    if(!allowed.has(id)){
     server=null;
     if(queued.length&&queued[0].operation!=='create'){
      for(const m of queued){ops.push(put('conflicts',{id:m.id,mutation:m,local_data:row.data,result:{status:'conflict',code:'deleted_or_unavailable',server_data:null}}),remove('outbox',m.id));remaining.delete(m.id)}
      ops.push(remove(name,id));oldIds.delete(id);continue;
     }
    }
    const active=queued.filter(m=>remaining.has(m.id)),data=overlay(server,active);
    if(data||active.length)ops.push(put(name,{id,version:server?.version||row.version||0,data,server_data:server,sync_status:active.length?'pending':'synced',deleted:data===null}));else ops.push(remove(name,id));oldIds.delete(id);
   }
   for(const id of oldIds)ops.push(remove(name,id));
  }
  if(r.projections)ops.push(put('meta',{id:'projections',data:{...((await this.store.get('meta','projections'))?.data||{}),...r.projections}}));
  ops.push(put('syncState',{id:'cursor',cursor:r.cursor,protocol_version:1,last_sync_at:new Date().toISOString()}));if(!this.stopped)await this.store.write(ops);
 }
 async resolve(id,choice,manual){
  return localLock(this.key,async()=>{
   const entry=await this.store.get('conflicts',id);if(!entry)return;const {mutation:m,result}=entry;
   if(choice==='server'){await this.store.write([remove('conflicts',id)]);emit(this);return}
   if(!result.server_data||!result.server_version)throw new Error('sync_entity_unavailable');
   const next={...m,id:uuid(),operation:m.operation,changes:manual||m.changes,base_version:result.server_version,state:'pending',attempted:false,order:Date.now()};next.mutation_id=next.id;delete next.data;if(next.operation!=='command'){delete next.command;delete next.args}if(next.operation!=='update')delete next.changes;
   await this.store.write([remove('conflicts',id),put('outbox',next)]);emit(this);this.schedule();
  });
 }
}
