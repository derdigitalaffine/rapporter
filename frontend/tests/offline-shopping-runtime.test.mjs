import 'fake-indexeddb/auto';
import {test,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {rememberOfflineBootstrap,setSyncTransport,offlineShoppingRequest,offlineMetadata,offlineEngine,clearOfflineIdentity} from '../src/offline-runtime.js';
const values=new Map();globalThis.localStorage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)};
Object.defineProperty(navigator,'onLine',{value:true,writable:true,configurable:true});
afterEach(async()=>{navigator.onLine=true;await clearOfflineIdentity();values.clear()});
function server(){const lists=[],items=[];let cursor=0;return {lists,items,async transport(p){const results=[];for(const m of p.mutations){const rows=m.entity_type==='shopping_list'?lists:items;const old=rows.find(r=>r.id===m.entity_id);if(m.operation==='create')rows.push({id:m.entity_id,version:1,checked:false,...m.data});else if(m.operation==='update'){Object.assign(old,m.changes);old.version++}else if(m.operation==='delete')rows.splice(rows.indexOf(old),1);results.push({mutation_id:m.mutation_id,status:'applied',version:old?.version||1,data:rows.find(r=>r.id===m.entity_id)});cursor++}return {protocol_version:1,mode:'snapshot',cursor,mutation_results:results,visibility:{task:[],task_list:[],event:[],shopping_list:lists.map(r=>r.id),shopping_item:items.map(r=>r.id)},snapshot:{shopping_lists:structuredClone(lists),shopping_items:structuredClone(items)}}}}}
async function setup(){const s=server();setSyncTransport(s.transport);await rememberOfflineBootstrap('/auth/session/',{authenticated:true,offline_sync_protocol:1,user:{id:crypto.randomUUID(),username:'Owner'}});await rememberOfflineBootstrap('/families/',{count:1,next:null,results:[{id:'f',name:'Family',memberships:[]}]});localStorage.setItem('famuhle-active-family','f');await offlineEngine('f').sync();return s}
const request=(path,method,body)=>offlineShoppingRequest(path,{method,body:body?JSON.stringify(body):undefined});
test('same local read/write path online and offline with final UUID and reload bootstrap',async()=>{
 const s=await setup(),e=offlineEngine('f');e.schedule=()=>{};navigator.onLine=false;
 const list=(await request('/shopping-lists/','POST',{family:'f',name:'Food'})).value;
 const item=(await request('/shopping-items/','POST',{shopping_list:list.id,name:'Milk'})).value;
 assert.match(item.id,/^[a-f0-9-]{36}$/);await request(`/shopping-items/${item.id}/`,'PATCH',{quantity:'2',checked:true});
 assert.equal((await request('/shopping-lists/','GET')).value[0].items[0].quantity,'2');assert.equal(offlineMetadata('/auth/session/').value.user.username,'Owner');
 assert.equal(offlineMetadata('/families/').value[0].id,'f');assert.equal(s.items.length,0);navigator.onLine=true;await e.sync();await e.sync();
 assert.equal(s.lists.length,1);assert.equal(s.items.length,1);assert.equal(s.items[0].checked,true);assert.equal((await e.store.list('outbox')).length,0);
 await request(`/shopping-items/${item.id}/`,'DELETE');assert.equal((await request('/shopping-lists/','GET')).value[0].items.length,0);await e.sync();assert.equal(s.items.length,0);
});
test('account switch stops old engines and clears all old private bootstrap/stores',async()=>{
 await setup();const old=offlineEngine('f');old.schedule=()=>{};await old.mutate('shopping_list',null,'create',{family:'f',name:'Private'});
 await rememberOfflineBootstrap('/auth/session/',{offline_sync_protocol:1,user:{id:'different',username:'Other'}});
 assert.equal(old.stopped,true);assert.equal((await old.store.list('outbox')).length,0);assert.equal(offlineMetadata('/families/').handled,false);assert.equal(offlineMetadata('/auth/session/').value.user.username,'Other');
});
test('servers without capability never activate the local domain adapter',async()=>{
 await rememberOfflineBootstrap('/auth/session/',{authenticated:true,user:{id:'old'}});
 assert.equal((await request('/shopping-lists/','GET')).handled,false);
});
test('quick-add keeps two explicit same-name items distinct instead of silently merging',async()=>{
 await setup();const e=offlineEngine('f');e.schedule=()=>{};navigator.onLine=false;
 const list=(await request('/shopping-lists/','POST',{family:'f',name:'Food'})).value;
 const first=(await request('/smart/shopping/quick-add/','POST',{family:'f',shopping_list:list.id,name:'Milk',quantity:'2'})).value;
 const again=(await request('/smart/shopping/quick-add/','POST',{family:'f',shopping_list:list.id,name:'milk',quantity:''})).value;
 assert.equal(first.reused,false);assert.equal(again.reused,false);assert.notEqual(again.item.id,first.item.id);assert.equal((await e.list('shopping_item')).length,2);
});

test('logout in another tab stops old writes without erasing the newly selected account',async()=>{
 await setup();const old=offlineEngine('f'),account=old.accountId;old.schedule=()=>{};
 await old.mutate('shopping_list',null,'create',{family:'f',name:'Unsent'});
 localStorage.setItem('familyos-offline-account','new-account');
 localStorage.setItem('familyos-offline-bootstrap:new-account',JSON.stringify({session:{user:{id:'new-account'}}}));
 const {clearRemoteOfflineAccount}=await import('../src/offline-runtime.js');await clearRemoteOfflineAccount(account);
 assert.equal(old.stopped,true);assert.equal((await old.store.list('outbox')).length,0);
 assert.equal(localStorage.getItem('familyos-offline-account'),'new-account');assert.notEqual(localStorage.getItem('familyos-offline-bootstrap:new-account'),null);
});
