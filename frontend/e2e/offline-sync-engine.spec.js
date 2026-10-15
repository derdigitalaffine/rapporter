import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
const engineSource=await readFile(new URL('../src/offline-sync-engine.js',import.meta.url),'utf8');
const storeSource=await readFile(new URL('../src/local-sync-store.js',import.meta.url),'utf8');
test.beforeEach(async({page})=>{
 await page.route('**/sync-engine-test',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><title>Sync engine test</title>'}));
 await page.route('**/offline-sync-engine.js',r=>r.fulfill({contentType:'text/javascript',body:engineSource}));
 await page.route('**/local-sync-store.js',r=>r.fulfill({contentType:'text/javascript',body:storeSource}));
 await page.goto('/sync-engine-test');
});
test('local writes survive offline reload with stable outbox identifiers',async({page,context})=>{
 await page.evaluate(async()=>{const {SyncEngine}=await import('/offline-sync-engine.js');const e=new SyncEngine('a','f');e.schedule=()=>{};const row=await e.mutate('task',null,'create',{title:'Offline task'});await e.mutate('task',row.id,'update',{notes:'Survives restart'});window.savedId=row.id});
 await context.setOffline(true);await context.setOffline(false);await page.reload();
 expect(await page.evaluate(async()=>{const {SyncEngine}=await import('/offline-sync-engine.js');const e=new SyncEngine('a','f');const rows=await e.store.list('outbox');return {count:rows.length,title:(await e.list('task'))[0].title,notes:rows[0].data.notes,same:rows[0].entity_id===(await e.list('task'))[0].id}})).toEqual({count:1,title:'Offline task',notes:'Survives restart',same:true});
});
test('lost response retries exact payload and never duplicates successful acknowledgement',async({page})=>{
 expect(await page.evaluate(async()=>{
  const {SyncEngine,TYPE_STORES}=await import('/offline-sync-engine.js');let first;let calls=0;const manifest=Object.fromEntries(Object.keys(TYPE_STORES).map(k=>[k,[]]));
  const e=new SyncEngine('a','f',async p=>{calls++;if(!first){first=JSON.stringify(p.mutations);throw new TypeError('lost reply')}if(first!==JSON.stringify(p.mutations))throw new Error('changed retry');const m=p.mutations[0];return {protocol_version:1,mode:'snapshot',cursor:1,visibility:{...manifest,task:[m.entity_id]},mutation_results:[{mutation_id:m.mutation_id,status:'already_applied',version:1}],snapshot:{tasks:[{id:m.entity_id,version:1,...m.data}]}}});e.schedule=()=>{};
  await e.mutate('task',null,'create',{title:'One task'});try{await e.sync()}catch{}clearTimeout(e.timer);await e.sync();e.stop();return {calls,count:(await e.list('task')).length,queued:(await e.store.list('outbox')).length};
 })).toEqual({calls:2,count:1,queued:0});
});
test('explicit account cleanup removes all families while preserving another account',async({page})=>{
 expect(await page.evaluate(async()=>{
  const {getSyncEngine,stopSyncAccount}=await import('/offline-sync-engine.js');
  for(const [accountId,familyId] of [['a','f'],['a','g'],['b','f']]){const e=getSyncEngine({accountId,familyId});e.schedule=()=>{};await e.mutate('task',null,'create',{title:accountId})}
  await stopSyncAccount('a');const {createLocalSyncStore}=await import('/local-sync-store.js');
  const result=await Promise.all([['a','f'],['a','g'],['b','f']].map(async([accountId,familyId])=>(await createLocalSyncStore({accountId,familyId}).list('outbox')).length));await stopSyncAccount('b');return result;
 })).toEqual([0,0,1]);
});
