import 'fake-indexeddb/auto';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {createLocalSyncStore,clearLocalSyncAccount,LOCAL_SYNC_DB,LOCAL_SYNC_VERSION} from '../src/local-sync-store.js';
import {requestBackgroundSync,storageDiagnostics,BACKGROUND_SYNC_TAG} from '../src/offline-recovery.js';

const request=r=>new Promise((resolve,reject)=>{r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});

test('v1 upgrade preserves attempted mutations, local conflicts and scopes while adding ordered lookup',async()=>{
 await request(indexedDB.deleteDatabase(LOCAL_SYNC_DB));
 const open=indexedDB.open(LOCAL_SYNC_DB,1);
 open.onupgradeneeded=()=>{
  for(const name of ['outbox','conflicts']){
   const store=open.result.createObjectStore(name,{keyPath:['accountId','familyId','id']});
   store.createIndex('scope',['accountId','familyId']);store.createIndex('account','accountId');
   if(name==='outbox')store.createIndex('entity',['accountId','familyId','entity_type','entity_id']);
  }
 };
 const db=await request(open),tx=db.transaction(['outbox','conflicts'],'readwrite');
 tx.objectStore('outbox').put({accountId:'a',familyId:'f',id:'attempted',mutation_id:'attempted',attempted:true,state:'sending',changes:{title:'Private draft'}});
 tx.objectStore('conflicts').put({accountId:'a',familyId:'f',id:'conflict',local_data:{title:'Keep both'},result:{server_data:{title:'Other'}}});
 await new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error)});db.close();
 const scoped=createLocalSyncStore({accountId:'a',familyId:'f'});
 const [mutation]=await scoped.list('outbox');
 assert.equal(mutation.attempted,true);assert.equal(mutation.state,'sending');assert.equal(mutation.changes.title,'Private draft');assert.equal(mutation.order,0);
 assert.equal((await scoped.get('conflicts','conflict')).local_data.title,'Keep both');
 const upgraded=await request(indexedDB.open(LOCAL_SYNC_DB));assert.equal(upgraded.version,LOCAL_SYNC_VERSION);assert.equal(upgraded.transaction('outbox').objectStore('outbox').indexNames.contains('scopeOrder'),true);upgraded.close();
 await clearLocalSyncAccount('a');
});

test('future local schema fails safely without deleting pending work',async()=>{
 const upgraded=await request(indexedDB.open(LOCAL_SYNC_DB,LOCAL_SYNC_VERSION+1));
 const tx=upgraded.transaction('outbox','readwrite');tx.objectStore('outbox').put({accountId:'a',familyId:'f',id:'preserve',order:1});
 await new Promise(resolve=>{tx.oncomplete=resolve});upgraded.close();
 await assert.rejects(createLocalSyncStore({accountId:'a',familyId:'f'}).list('outbox'),{name:'VersionError'});
 const db=await request(indexedDB.open(LOCAL_SYNC_DB));assert.equal((await request(db.transaction('outbox').objectStore('outbox').get(['a','f','preserve']))).id,'preserve');db.close();
 await request(indexedDB.deleteDatabase(LOCAL_SYNC_DB));
});

test('Background Sync is optional and carries no account data',async()=>{
 assert.equal(await requestBackgroundSync(null),false);
 assert.equal(await requestBackgroundSync({ready:Promise.resolve({})}),false);
 assert.equal(await requestBackgroundSync({ready:Promise.resolve({sync:{register:async()=>{throw new Error('denied')}}})}),false);
 const tags=[];assert.equal(await requestBackgroundSync({ready:Promise.resolve({sync:{register:async tag=>tags.push(tag)}})}),true);assert.deepEqual(tags,[BACKGROUND_SYNC_TAG]);
});

test('storage diagnostics tolerate denied/unsupported APIs and report low space without throwing',async()=>{
 assert.equal((await storageDiagnostics(null)).supported,false);
 const denied={persisted:async()=>{throw new Error('denied')},estimate:async()=>{throw new Error('quota')}};
 assert.deepEqual(await storageDiagnostics(denied),{supported:true,persistent:null,usage:null,quota:null,lowSpace:false});
 const result=await storageDiagnostics({persisted:async()=>false,estimate:async()=>({usage:95,quota:100})});
 assert.equal(result.lowSpace,true);assert.equal(result.persistent,false);
});

test('service-worker sync wakes windows without private fetches or outbox acknowledgements',async()=>{
 const listeners={},messages=[];
 const self={addEventListener:(name,fn)=>{listeners[name]=fn},clients:{matchAll:async()=>[{postMessage:message=>messages.push(message)}]}};
 const source=await readFile(new URL('../public/sw.js',import.meta.url),'utf8');
 vm.runInNewContext(source,{self,fetch:()=>{throw new Error('No private background HTTP allowed')}});
 let completed;listeners.sync({tag:BACKGROUND_SYNC_TAG,waitUntil:promise=>{completed=promise}});await completed;
 assert.deepEqual(JSON.parse(JSON.stringify(messages)),[{type:'FAMILYOS_SYNC_WAKE'}]);
});
