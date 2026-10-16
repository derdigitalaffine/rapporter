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

test('quiet LED remains steady during routine empty-queue checks and preserves real health changes',async()=>{
 const {syncIndicator}=await import('../src/offline-status.js');
 const health={online:true,serverState:'reachable',liveState:'connected',lastSyncAt:new Date().toISOString()};
 assert.equal(syncIndicator({...health,state:'synced'}),'ready');
 assert.equal(syncIndicator({...health,state:'synchronizing'}),'ready');
 assert.equal(syncIndicator({...health,state:'synchronizing',pending:1}),'attention');
 assert.equal(syncIndicator({...health,state:'synced',conflicts:1}),'attention');
 assert.equal(syncIndicator({...health,state:'synchronizing',serverState:'unreachable'}),'error');
 assert.equal(syncIndicator({...health,state:'synced',liveState:'reconnecting'}),'attention');
 assert.equal(syncIndicator({...health,state:'synchronizing',liveState:'reconnecting'}),'attention');
 assert.equal(syncIndicator({...health,state:'synced',online:false}),'offline');
 assert.equal(syncIndicator({...health,state:'synced',serverState:'auth-required'}),'error');
 assert.equal(syncIndicator({...health,state:'synchronizing',serverState:'unknown'}),'checking');
 assert.equal(syncIndicator({...health,state:'synced',lastSyncAt:new Date(Date.now()-60001).toISOString()}),'checking');
});


test('server rejection presentation preserves bounded error details and differs from field conflicts',async()=>{
 const {rejectionLines,canRetryRejectedCreate}=await import('../src/offline-rejections.js');
 const result={status:'rejected',code:'permission_denied',http_status:403,errors:{participants:['Custody required'],detail:'Denied'}};
 assert.deepEqual(rejectionLines(result),['participants: Custody required','Denied']);
 assert.equal(syncStatus({conflicts:0,rejected:1}),'rejected');assert.equal(syncStatus({conflicts:1}),'attention');
 assert.ok(canRetryRejectedCreate({result,mutation:{entity_type:'event',operation:'create',data:{type:'calendar.event'}}}));
 assert.equal(rejectionLines({errors:Array(100).fill('error')}).length,20);
});

test('HTTP permission failures preserve server reason across reload without pretending the session expired',async()=>{
 const account=crypto.randomUUID();let fail=true;
 const e=new SyncEngine(account,'family',async()=>{
  if(fail)throw Object.assign(new Error('Family access denied'),{status:403,code:'permission_denied'});
  return {protocol_version:1,mode:'snapshot',cursor:1,visibility:Object.fromEntries(Object.keys(TYPE_STORES).map(k=>[k,[]])),snapshot:{}};
 });e.schedule=()=>{};
 try{
  await e.mutate('event',null,'create',{type:'calendar.event',title:'Saved locally'});
  await assert.rejects(e.sync(),/Family access denied/);
  assert.equal(e.serverState,'reachable');assert.equal(e.state,'request-error');
  assert.equal((await e.store.get('syncState','lastError')).error.message,'Family access denied');
  assert.equal((await e.store.list('outbox')).length,1);assert.equal((await e.store.list('conflicts')).length,0);
  assert.equal(syncStatus({requestError:e.lastError,serverState:'reachable'}),'rejected');
  fail=false;await e.sync();assert.equal(e.lastError,null);assert.equal(await e.store.get('syncState','lastError'),null);
 }finally{e.stop();await clearLocalSyncAccount(account)}
});
