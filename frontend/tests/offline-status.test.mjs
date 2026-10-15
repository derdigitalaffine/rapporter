import 'fake-indexeddb/auto';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {syncStatus} from '../src/offline-status.js';
import {SyncEngine,TYPE_STORES} from '../src/offline-sync-engine.js';
import {clearLocalSyncAccount} from '../src/local-sync-store.js';
import {syncLabels} from '../src/offline-status-i18n.js';

test('unconfirmed, failed or stale server state never means synced even with no pending writes',()=>{
 const now=Date.now(),lastSyncAt=new Date(now).toISOString();
 assert.equal(syncStatus({online:true}), 'checking');
 assert.equal(syncStatus({online:true,state:'synced',lastSyncAt,now}), 'checking');
 assert.equal(syncStatus({online:true,state:'synced',serverState:'unreachable',lastSyncAt,now}), 'serverDown');
 assert.equal(syncStatus({online:true,state:'synced',serverState:'reachable',lastSyncAt,now:now+60001}), 'checking');
 assert.equal(syncStatus({online:true,state:'synced',serverState:'reachable',lastSyncAt,now}), 'sync');
 assert.equal(syncStatus({online:false,state:'synced',serverState:'reachable',lastSyncAt,now}), 'offline');
});

test('real server failure while browser stays online preserves drafts and historical sync time',async()=>{
 const account=crypto.randomUUID();let fail=false;
 const e=new SyncEngine(account,'family',async()=>{if(fail)throw new TypeError('server down');return {protocol_version:1,mode:'snapshot',cursor:1,visibility:Object.fromEntries(Object.keys(TYPE_STORES).map(k=>[k,[]])),snapshot:{}}});e.schedule=()=>{};
 try{
  await e.sync();const last=e.lastSyncAt;assert.equal(e.serverState,'reachable');fail=true;
  await e.mutate('task',null,'create',{title:'Keep this draft'});await assert.rejects(e.sync(),/server down/);clearTimeout(e.timer);
  assert.equal(e.serverState,'unreachable');assert.equal(e.lastSyncAt,last);assert.equal((await e.store.list('outbox')).length,1);assert.equal((await e.list('task'))[0].title,'Keep this draft');
 }finally{e.stop();await clearLocalSyncAccount(account)}
});

test('hung request times out and aborts transport without acknowledging its mutation',async()=>{
 const account=crypto.randomUUID();let signal;const e=new SyncEngine(account,'family',async(payload,received)=>{signal=received;return new Promise(()=>{})});e.schedule=()=>{};e.requestTimeoutMs=5;
 try{await e.mutate('task',null,'create',{title:'Pending'});await assert.rejects(e.sync(),/sync_timeout/);clearTimeout(e.timer);assert.equal(signal.aborted,true);assert.equal(e.serverState,'unreachable');assert.equal((await e.store.list('outbox')).length,1)}finally{e.stop();await clearLocalSyncAccount(account)}
});

test('new status and recovery controls have complete labels in all supported languages',()=>{
 const keys=Object.keys(syncLabels.en);for(const language of ['de','en','fr','nl','th'])for(const key of keys)assert.equal(typeof syncLabels[language][key],'string',`${language}.${key}`);
});
