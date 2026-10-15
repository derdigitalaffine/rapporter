import {test} from 'node:test';
import assert from 'node:assert/strict';
import {LiveSyncCoordinator,routeEngineThrough} from '../src/offline-live.js';

const timers={setInterval:()=>1,clearInterval(){},setTimeout(fn){fn();return 1},clearTimeout(){}};
const storage=()=>{const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k)}};
class FakeChannel{
 static all=new Map();
 constructor(name){this.name=name;const list=FakeChannel.all.get(name)||[];list.push(this);FakeChannel.all.set(name,list)}
 postMessage(data){for(const peer of FakeChannel.all.get(this.name)||[])if(peer!==this)peer.onmessage?.({data})}
 close(){FakeChannel.all.set(this.name,(FakeChannel.all.get(this.name)||[]).filter(x=>x!==this))}
}
class FakeSocket{
 static instances=[];
 constructor(url){this.url=url;FakeSocket.instances.push(this)}
 close(){this.closed=true;this.onclose?.()}
 message(data){this.onmessage?.({data:JSON.stringify(data)})}
}
const engine=()=>{const state={calls:0,schedules:0};return {state,async sync(){state.calls++},schedule(){state.schedules++}}};

test('one tab leads, followers request sync and leader loss is taken over',async()=>{
 FakeChannel.all.clear();FakeSocket.instances=[];const shared=storage(),a=engine(),b=engine();
 const first=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:a,storage:shared,Channel:FakeChannel,Socket:FakeSocket,timers}).start();
 const second=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:b,storage:shared,Channel:FakeChannel,Socket:FakeSocket,timers}).start();
 assert.equal(first.isLeader(),true);assert.equal(second.isLeader(),false);a.state.calls=0;b.state.calls=0;
 second.requestSync();assert.equal(a.state.calls,1);assert.equal(b.state.calls,0);
 first.stop();second.checkLease();assert.equal(second.isLeader(),true);assert.equal(b.state.calls,1);
 second.stop();
});

test('sync_available is wake-up only and triggers authoritative HTTP engine sync',async()=>{
 FakeChannel.all.clear();FakeSocket.instances=[];const e=engine(),coordinator=new LiveSyncCoordinator({accountId:'a',familyId:'family',engine:e,storage:storage(),Channel:FakeChannel,Socket:FakeSocket,timers}).start();
 e.state.calls=0;const socket=FakeSocket.instances.at(-1);assert.match(socket.url,/\/ws\/sync\/family\/$/);
 socket.message({type:'sync_available',family_id:'family',cursor:42});assert.equal(e.state.calls,1);
 socket.message({type:'domain_payload',entity:{secret:'never'}});assert.equal(e.state.calls,1);coordinator.stop();
});

test('follower engine never sends HTTP directly; explicit leader path still works',async()=>{
 const e=engine(),coordinator={isLeader:()=>false,requestSync(){this.requests=(this.requests||0)+1}};routeEngineThrough(coordinator,e);
 await e.sync();assert.equal(e.state.calls,0);assert.equal(coordinator.requests,1);
 e.schedule();assert.equal(e.state.calls,0);assert.equal(coordinator.requests,2);
 await e.sync({leader:true});assert.equal(e.state.calls,1);
});

test('WebSocket absence does not disable leader HTTP synchronization',async()=>{
 const e=engine(),coordinator=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:e,storage:storage(),Channel:null,Socket:null,timers}).start();
 e.state.calls=0;coordinator.requestSync();assert.equal(e.state.calls,1);coordinator.stop();
});

test('closed WebSocket reconnects on the next lease heartbeat',()=>{
 FakeSocket.instances=[];const e=engine(),coordinator=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:e,storage:storage(),Channel:null,Socket:FakeSocket,timers}).start();
 const first=FakeSocket.instances.at(-1);first.close();coordinator.checkLease();
 assert.equal(FakeSocket.instances.length,2);assert.notEqual(coordinator.socket,first);
 coordinator.stop();coordinator.checkLease();assert.equal(FakeSocket.instances.length,2);
});

test('blocked storage degrades to independent HTTP sync instead of breaking startup',()=>{
 const blocked={getItem(){throw new Error('SecurityError')},setItem(){throw new Error('SecurityError')}};
 const e=engine(),coordinator=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:e,storage:blocked,Channel:null,Socket:null,timers}).start();
 assert.equal(coordinator.isLeader(),true);assert.equal(e.state.calls,1);
 coordinator.requestSync();assert.equal(e.state.calls,2);coordinator.stop();
});

test('leader HTTP completion refreshes follower state without another HTTP request',async()=>{
 FakeChannel.all.clear();const shared=storage(),a=engine(),b=engine();a.state='synced';
 const first=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:a,storage:shared,Channel:FakeChannel,Socket:null,timers}).start();
 const second=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:b,storage:shared,Channel:FakeChannel,Socket:null,timers}).start();
 const followerCalls=b.state;let notified=0;second.notifyLocal=state=>{notified++;b.state=state};
 await Promise.resolve();assert.equal(notified,1);assert.equal(b.state,'synced');assert.equal(followerCalls.calls,0);
 first.stop();second.stop();
});

test('live status requires socket open; disconnect probes HTTP and propagates interruption',async()=>{
 FakeSocket.instances=[];const e=engine(),coordinator=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:e,storage:storage(),Channel:null,Socket:FakeSocket,timers}).start();
 const socket=FakeSocket.instances.at(-1);assert.equal(e.liveState,'connecting');socket.onopen();assert.equal(e.liveState,'connected');
 const before=e.state.calls;socket.close();assert.equal(e.liveState,'reconnecting');assert.equal(e.state.calls,before+1);
 coordinator.stop();
});

test('leader checks HTTP every thirty seconds even while an apparently open socket is idle',()=>{
 let now=0;const e=engine(),coordinator=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:e,storage:storage(),Channel:null,Socket:FakeSocket,timers,now:()=>now}).start();
 const before=e.state.calls;now=29000;coordinator.checkLease();assert.equal(e.state.calls,before);now=30000;coordinator.checkLease();assert.equal(e.state.calls,before+1);coordinator.stop();
});

test('failed reconnect attempts retain one visible interrupted state until socket really opens',async()=>{
 FakeSocket.instances=[];FakeChannel.all.clear();const shared=storage(),a=engine(),b=engine();
 const leader=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:a,storage:shared,Channel:FakeChannel,Socket:FakeSocket,timers}).start();
 const follower=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:b,storage:shared,Channel:FakeChannel,Socket:FakeSocket,timers}).start();
 const first=leader.socket;assert.equal(a.liveState,'connecting');first.onerror();first.close();
 assert.equal(a.liveState,'reconnecting');assert.equal(b.liveState,'reconnecting');
 for(let attempt=0;attempt<5;attempt++){
  leader.checkLease();assert.equal(a.liveState,'reconnecting');assert.equal(b.liveState,'reconnecting');
  leader.socket.onerror();leader.socket.close();await Promise.resolve();
  assert.equal(a.liveState,'reconnecting');assert.equal(b.liveState,'reconnecting');
 }
 leader.checkLease();assert.equal(a.liveState,'reconnecting');leader.socket.onopen();
 assert.equal(a.liveState,'connected');assert.equal(b.liveState,'connected');
 leader.stop();follower.stop();
});

test('constructor failures do not flash connecting during later transport retries',()=>{
 let attempts=0;class FailingSocket{constructor(){attempts++;throw new Error('unsupported')}}
 const e=engine(),leader=new LiveSyncCoordinator({accountId:'a',familyId:'f',engine:e,storage:storage(),Channel:null,Socket:FailingSocket,timers}).start();
 const transitions=[];const set=leader.setLiveState.bind(leader);leader.setLiveState=value=>{if(e.liveState!==value)transitions.push(value);set(value)};
 for(let i=0;i<5;i++)leader.checkLease();
 assert.equal(attempts,6);assert.equal(e.liveState,'unavailable');assert.deepEqual(transitions,[]);leader.stop();
});
