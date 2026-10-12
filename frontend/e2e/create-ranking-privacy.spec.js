import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

// Exercise production persistence with deterministic network and browser storage.
function client(){
 const storage={};
 Object.defineProperties(storage,{
  getItem:{value:key=>storage[key]??null},
  setItem:{value:(key,value)=>{storage[key]=String(value)}},
  removeItem:{value:key=>{delete storage[key]}},
 });
 const listeners=new Map(),events=[],requests=[];
 const sandbox={localStorage:storage,crypto:globalThis.crypto,Uint8Array,Date,console,
  AUTH_CHANGED_EVENT:'auth-changed',
  window:{addEventListener:(key,fn)=>listeners.set(key,fn),dispatchEvent:event=>events.push(event)},
  CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail}},
  api:(path,options)=>{requests.push({path,options});return sandbox.respond(path,options)},
  respond:async()=>({preferences:{pinned_action_ids:['event']},stats:[]}),
 };
 vm.createContext(sandbox);
 const ranking=readFileSync(new URL('../src/create-actions.js',import.meta.url),'utf8').replace(/^import .*;\n/gm,'').replace(/export /g,'');
 const source=readFileSync(new URL('../src/create-ranking-client.js',import.meta.url),'utf8').replace(/^import .*;\n/gm,'').replace(/export /g,'');
 vm.runInContext(`${ranking}\n${source}\nthis.client={setCreateRankingIdentity,createRankingScope,loadCachedCreateRanking,fetchCreateRanking,recordCreateUsage,flushCreateUsageQueue,patchCreateRanking};`,sandbox);
 return {...sandbox.client,storage,events,requests,setResponse:fn=>{sandbox.respond=fn},logout:()=>listeners.get('auth-changed')({detail:{authenticated:false}})};
}
const scope=(userId='1',membershipId='m1',familyId='f1')=>({userId,membershipId,familyId});
const pending=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}};
const usage=s=>({scope:s,actionId:'task',originPage:'home'});
const queueKey=s=>`famuhle-create-usage:v2:${JSON.stringify([s.userId,s.membershipId,s.familyId])}`;

test('ranking cache requires verified user, membership and family and discards ownerless data',async()=>{
 const c=client();c.storage.setItem('famuhle-create-ranking:f1',JSON.stringify({preferences:{direct_mode:true}}));c.storage.setItem('famuhle-create-usage:f1','[]');
 expect(c.loadCachedCreateRanking(scope()).preferences.direct_mode).toBe(false);
 c.setCreateRankingIdentity(1);expect(c.storage.getItem('famuhle-create-ranking:f1')).toBeNull();expect(c.storage.getItem('famuhle-create-usage:f1')).toBeNull();
 await c.fetchCreateRanking(scope());expect(c.loadCachedCreateRanking(scope()).preferences.pinned_action_ids).toEqual(['event']);
 expect(c.loadCachedCreateRanking(scope('1','m2')).preferences.pinned_action_ids).toEqual([]);
 expect(c.loadCachedCreateRanking(scope('1','m1','f2')).preferences.pinned_action_ids).toEqual([]);
 c.setCreateRankingIdentity(2);expect(c.loadCachedCreateRanking(scope('2','m2')).preferences.pinned_action_ids).toEqual([]);
 expect(c.loadCachedCreateRanking(scope()).preferences.pinned_action_ids).toEqual([]);
 expect(c.createRankingScope({id:'f1',memberships:[{id:'m1',user:1}]},2)).toBeNull();
});

test('logout invalidates delayed profiles and failed usage without recreating private storage',async()=>{
 const c=client();c.setCreateRankingIdentity(1);const fetch=pending();c.setResponse(()=>fetch.promise);const response=c.fetchCreateRanking(scope());c.logout();c.setCreateRankingIdentity(2);fetch.resolve({preferences:{direct_mode:true},stats:[]});expect(await response).toBeNull();expect(Object.keys(c.storage)).toEqual([]);
 c.setCreateRankingIdentity(1);const post=pending();c.setResponse(()=>post.promise);const recorded=c.recordCreateUsage(usage(scope())).catch(()=>null);c.logout();post.reject(new Error('offline'));await recorded;expect(Object.keys(c.storage)).toEqual([]);
});

test('offline receipts are never replayed by another account or membership',async()=>{
 const c=client();c.setCreateRankingIdentity(1);c.setResponse(async()=>{throw new Error('offline')});await c.recordCreateUsage(usage(scope())).catch(()=>{});expect(JSON.parse(c.storage.getItem(queueKey(scope())))).toHaveLength(1);
 const count=c.requests.length;c.setCreateRankingIdentity(2);await c.flushCreateUsageQueue(scope());await c.flushCreateUsageQueue(scope('2','m2'));expect(c.requests).toHaveLength(count);
 c.setCreateRankingIdentity(1);await c.flushCreateUsageQueue(scope('1','rejoined'));expect(c.requests).toHaveLength(count);
 c.setResponse(async()=>({stats:[]}));await c.flushCreateUsageQueue(scope());expect(c.requests).toHaveLength(count+1);expect(c.storage.getItem(queueKey(scope()))).toBeNull();
});

test('membership denial clears cached profile and all queued receipts without further replay',async()=>{
 const c=client();c.setCreateRankingIdentity(1);c.setResponse(async()=>{throw new Error('offline')});await c.recordCreateUsage(usage(scope())).catch(()=>{});await c.recordCreateUsage(usage(scope())).catch(()=>{});
 const count=c.requests.length;c.setResponse(async()=>{throw Object.assign(new Error('forbidden'),{status:403})});await c.flushCreateUsageQueue(scope());expect(c.requests).toHaveLength(count+1);expect(Object.keys(c.storage)).toEqual([]);
});

test('concurrent replay keeps new signals and deduplicates the in-flight replay',async()=>{
 const c=client();c.setCreateRankingIdentity(1);c.setResponse(async()=>{throw new Error('offline')});await c.recordCreateUsage(usage(scope())).catch(()=>{});const replay=pending();c.setResponse(()=>replay.promise);const count=c.requests.length;const first=c.flushCreateUsageQueue(scope());const second=c.flushCreateUsageQueue(scope());expect(c.requests).toHaveLength(count+1);
 c.setResponse(async()=>{throw new Error('offline')});await c.recordCreateUsage(usage(scope())).catch(()=>{});replay.resolve({stats:[]});await Promise.all([first,second]);expect(JSON.parse(c.storage.getItem(queueKey(scope())))).toHaveLength(1);
});
