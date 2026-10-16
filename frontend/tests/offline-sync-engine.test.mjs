import 'fake-indexeddb/auto';
import {test,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {SyncEngine,TYPE_STORES,stopSyncAccount} from '../src/offline-sync-engine.js';
import {createLocalSyncStore,clearLocalSyncAccount} from '../src/local-sync-store.js';
const active=[];
const empty=()=>Object.fromEntries(Object.keys(TYPE_STORES).map(k=>[k,[]]));
function engine(transport){const account=crypto.randomUUID();const e=new SyncEngine(account,'family',transport);active.push(e);return e}
function snapshot(items=[]){return {protocol_version:1,mode:'snapshot',cursor:1,mutation_results:[],visibility:{...empty(),shopping_item:items.map(x=>x.id)},snapshot:{shopping_items:items}}}
afterEach(async()=>{for(const e of active.splice(0)){e.stop();await e.inflight?.catch(()=>{});await clearLocalSyncAccount(e.accountId)}});
test('create/update compact, persist across reopen and create/delete cancels',async()=>{
 const e=engine();e.schedule=()=>{};
 const item=await e.mutate('shopping_item',null,'create',{name:'Milk',shopping_list:'list'});
 await e.mutate('shopping_item',item.id,'update',{name:'Oat milk'});
 const reopened=createLocalSyncStore({accountId:e.accountId,familyId:e.familyId});
 assert.equal((await reopened.list('outbox')).length,1);assert.equal((await reopened.list('outbox'))[0].data.name,'Oat milk');
 assert.equal((await reopened.list('shoppingItems'))[0].data.name,'Oat milk');
 await e.mutate('shopping_item',item.id,'delete');assert.deepEqual(await e.list('shopping_item'),[]);assert.deepEqual(await reopened.list('outbox'),[]);
});
test('lost response preserves stable attempted mutation; new edits do not change it',async()=>{
 let received;const e=engine(async payload=>{received=payload;throw new TypeError('offline')});e.schedule=()=>{};
 await e.install(snapshot([{id:'i',version:1,name:'Milk'}]),[]);
 await e.mutate('shopping_item','i','update',{name:'Tea'});await assert.rejects(e.sync());clearTimeout(e.timer);
 const original=received.mutations[0];await e.mutate('shopping_item','i','update',{name:'Coffee'});
 const rows=await e.store.list('outbox');assert.equal(rows.length,2);assert.equal(rows.find(x=>x.id===original.mutation_id).changes.name,'Tea');
 assert.equal(rows.find(x=>x.id===original.mutation_id).attempted,true);assert.equal((await e.get('shopping_item','i')).name,'Coffee');
});
test('snapshot reset preserves pending work and field conflicts preserve both values',async()=>{
 const e=engine();e.schedule=()=>{};await e.install(snapshot([{id:'i',version:1,name:'Milk'}]),[]);
 await e.mutate('shopping_item','i','update',{name:'Tea'});
 await e.install({...snapshot([{id:'i',version:2,name:'Coffee'}]),cursor:99},[]);
 assert.equal((await e.get('shopping_item','i')).name,'Tea');assert.equal((await e.store.list('outbox')).length,1);
 const sent=await e.store.list('outbox');await e.install({protocol_version:1,mode:'delta',cursor:100,visibility:{...empty(),shopping_item:['i']},changes:[],mutation_results:[{mutation_id:sent[0].id,status:'conflict',server_data:{id:'i',version:2,name:'Coffee'},server_version:2,conflicts:{name:{client:'Tea',server:'Coffee'}}}]},sent);
 const [conflict]=await e.store.list('conflicts');assert.equal(conflict.local_data.name,'Tea');assert.equal(conflict.result.server_data.name,'Coffee');assert.equal((await e.get('shopping_item','i')).name,'Coffee');
});
test('revocation clears readable local data and preserves unsent work in conflicts',async()=>{
 const e=engine();e.schedule=()=>{};await e.install(snapshot([{id:'i',version:1,name:'Milk'}]),[]);await e.mutate('shopping_item','i','update',{quantity:'2'});
 await e.install({protocol_version:1,mode:'delta',cursor:2,visibility:empty(),changes:[],mutation_results:[]},[]);
 assert.deepEqual(await e.list('shopping_item'),[]);assert.equal((await e.store.list('conflicts'))[0].local_data.quantity,'2');assert.deepEqual(await e.store.list('outbox'),[]);
});
test('authentication failure pauses sync without losing local work; read-only calendar rejects writes',async()=>{
 const e=engine(async()=>{throw Object.assign(new Error('auth'),{status:401})});e.schedule=()=>{};await e.mutate('task',null,'create',{title:'Work'});
 await assert.rejects(e.sync());assert.equal(e.state,'auth-required');assert.equal((await e.store.list('outbox')).length,1);
 await e.install({...snapshot(),visibility:{...empty(),event:['external']},snapshot:{events:[{id:'external',version:1,read_only:true,title:'ICS'}]}},[]);
 await assert.rejects(e.mutate('event','external','update',{title:'No'}),/read_only_source/);
});
test('unsupported response cannot acknowledge pending mutations or advance cursor',async()=>{
 const e=engine(async()=>({protocol_version:2,mode:'delta',cursor:999}));e.schedule=()=>{};await e.mutate('task',null,'create',{title:'Work'});
 await assert.rejects(e.sync(),/unsupported_sync_protocol/);clearTimeout(e.timer);
 assert.equal((await e.store.list('outbox')).length,1);assert.equal(await e.store.get('syncState','cursor'),null);
});

test('keeping a conflict draft updates the local entity immediately and durably before network sync',async()=>{
 const e=engine();e.schedule=()=>{};await e.install(snapshot([{id:'i',version:1,name:'Milk'}]),[]);
 await e.mutate('shopping_item','i','update',{name:'Tea'});const sent=await e.store.list('outbox');
 await e.install({protocol_version:1,mode:'delta',cursor:2,visibility:{...empty(),shopping_item:['i']},changes:[{entity_type:'shopping_item',entity_id:'i',version:2,operation:'update',data:{id:'i',version:2,name:'Coffee'}}],mutation_results:[{mutation_id:sent[0].id,status:'conflict',server_data:{id:'i',version:2,name:'Coffee'},server_version:2,conflicts:{name:{client:'Tea',server:'Coffee'}}}]},sent);
 assert.equal((await e.get('shopping_item','i')).name,'Coffee');
 await e.resolve(sent[0].id,'local');assert.equal((await e.get('shopping_item','i')).name,'Tea');
 const row=await createLocalSyncStore({accountId:e.accountId,familyId:e.familyId}).get('shoppingItems','i');
 assert.equal(row.data.name,'Tea');assert.equal(row.server_data.name,'Coffee');assert.equal(row.sync_status,'pending');
 assert.deepEqual(await e.store.list('conflicts'),[]);const [retry]=await e.store.list('outbox');assert.notEqual(retry.id,sent[0].id);assert.equal(retry.base_version,2);assert.equal(retry.attempted,false);
});


test('rejected appointment survives reopening and explicit retry keeps final UUID and latest draft',async()=>{
 const e=engine();e.schedule=()=>{};
 const event=await e.mutate('event',null,'create',{type:'calendar.event',family:'family',title:'Child visit',participants:['child'],starts_at:'2026-10-20T10:00:00Z'});
 const sent=await e.store.list('outbox');
 await e.store.write(sent.map(m=>({store:'outbox',type:'put',value:{...m,attempted:true,state:'sending'}})));
 await e.mutate('event',event.id,'update',{title:'Latest child visit'});
 await e.install({...snapshot(),mutation_results:[{mutation_id:sent[0].id,status:'rejected',code:'permission_denied',http_status:403,errors:'Custody required'}]},sent);
 const reopened=createLocalSyncStore({accountId:e.accountId,familyId:e.familyId});
 const entry=(await reopened.list('conflicts')).find(row=>row.id===sent[0].id);
 assert.equal(entry.result.http_status,403);assert.equal(entry.local_data.title,'Latest child visit');
 assert.equal((await reopened.list('outbox')).length,0);
 await e.resolve(entry.id,'retry');
 const [retry]=await reopened.list('outbox');
 assert.equal(retry.entity_id,event.id);assert.notEqual(retry.mutation_id,sent[0].id);assert.equal(retry.data.title,'Latest child visit');assert.deepEqual(retry.data.participants,['child']);
 assert.equal(retry.attempted,false);assert.equal((await e.get('event',event.id)).title,'Latest child visit');
 // No implicit resolution of any other local work preserved for this entity.
 assert.equal((await reopened.list('conflicts')).length,1);
 e.transport=async payload=>{const m=payload.mutations[0],data={...m.data,id:m.entity_id,version:1};return {...snapshot(),visibility:{...empty(),event:[event.id]},snapshot:{events:[data]},mutation_results:[{mutation_id:m.mutation_id,status:'applied',version:1,data}]}};
 await e.sync();assert.equal((await reopened.list('outbox')).length,0);assert.equal((await e.list('event')).length,1);
});

test('unavailable UUIDs and genuine conflicts cannot be replayed as new appointments',async()=>{
 const e=engine();e.schedule=()=>{};
 for(const result of [{status:'rejected',code:'id_unavailable'},{status:'conflict',code:'deleted_or_unavailable'}]){
  const id=crypto.randomUUID(),m={id,mutation_id:id,entity_id:crypto.randomUUID(),entity_type:'event',operation:'create',data:{type:'calendar.event',title:'Keep safely'}};
  await e.store.write([{store:'conflicts',type:'put',value:{id,mutation:m,result,local_data:m.data}}]);
  await assert.rejects(e.resolve(id,'retry'),/sync_retry_unavailable/);assert.ok(await e.store.get('conflicts',id));
 }
 assert.equal((await e.store.list('outbox')).length,0);
});
