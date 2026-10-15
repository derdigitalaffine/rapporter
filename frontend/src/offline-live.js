const coordinators=new Map();
const LEASE_MS=5000, HEARTBEAT_MS=2000, PROBE_MS=30000;
const parse=value=>{try{return JSON.parse(value||'null')}catch{return null}};

export class LiveSyncCoordinator{
 constructor({accountId,familyId,engine,storage=globalThis.localStorage,Channel=globalThis.BroadcastChannel,Socket=globalThis.WebSocket,now=()=>Date.now(),timers=globalThis}={}){
  Object.assign(this,{accountId:String(accountId),familyId:String(familyId),engine,storage,Channel,Socket,now,timers});
  this.id=globalThis.crypto?.randomUUID?.()||`${Math.random()}`;this.key=`familyos-sync-leader:${this.accountId}:${this.familyId}`;this.requestKey=`${this.key}:request`;this.stateKey=`${this.key}:state`;this.channelName=`familyos-sync:${this.accountId}:${this.familyId}`;this.leader=false;this.stopped=false;this.socket=null;this.lastProbe=-Infinity;
 }
 isLeader(){return this.leader&&!this.stopped}
 start(){
  if(this.stopped)return this;this.stopped=false;
  if(this.Channel){try{this.channel=new this.Channel(this.channelName);this.channel.onmessage=e=>{if(e.data?.type==='sync-request'&&this.isLeader())this.runLeaderSync();if(e.data?.type==='sync-complete'&&!this.isLeader())this.notifyLocal(e.data.state,e.data)}}catch{}}
  this.storageHandler=e=>{if(e.key===this.requestKey&&this.isLeader())this.runLeaderSync();if(e.key===this.key)this.checkLease();if(e.key===this.stateKey&&!this.isLeader())this.notifyLocal(parse(e.newValue)?.state,parse(e.newValue)||{})};
  globalThis.addEventListener?.('storage',this.storageHandler);this.checkLease();this.timer=this.timers.setInterval?.(()=>this.checkLease(),HEARTBEAT_MS);return this;
 }
 checkLease(){
  if(this.stopped)return;let current=null;try{current=parse(this.storage?.getItem?.(this.key))}catch{}const time=this.now();
  if(this.leader){if(current&&current.owner!==this.id&&current.expires>time){this.stepDown();return}this.writeLease();this.openSocket();if(time-this.lastProbe>=PROBE_MS)this.runLeaderSync();return}
  if(!current||current.expires<=time||current.owner===this.id){this.leader=true;this.writeLease();this.openSocket();this.runLeaderSync()}
 }
 writeLease(){try{this.storage?.setItem?.(this.key,JSON.stringify({owner:this.id,expires:this.now()+LEASE_MS}))}catch{}}
 requestSync(){
  if(this.stopped)return;if(this.isLeader()){this.timers.clearTimeout?.(this.syncTimer);this.syncTimer=this.timers.setTimeout?.(()=>this.runLeaderSync(),30);return}
  try{this.channel?.postMessage?.({type:'sync-request'})}catch{}
  try{this.storage?.setItem?.(this.requestKey,JSON.stringify({from:this.id,at:this.now()}))}catch{}
  this.checkLease();
 }
 publishStatus(){
  if(!this.isLeader())return;const message={type:'sync-complete',state:this.engine.state,serverState:this.engine.serverState,lastSyncAt:this.engine.lastSyncAt,liveState:this.engine.liveState,at:this.now()};
  try{this.channel?.postMessage?.(message)}catch{}try{this.storage?.setItem?.(this.stateKey,JSON.stringify(message))}catch{}
 }
 runLeaderSync(){if(this.isLeader()){this.lastProbe=this.now();this.engine.sync({leader:true}).then(()=>this.publishStatus(),()=>this.publishStatus())}}
 notifyLocal(state,health={}){if(this.stopped)return;if(typeof state==='string')this.engine.state=state;for(const key of ['serverState','lastSyncAt','liveState'])if(health[key]!==undefined)this.engine[key]=health[key];globalThis.window?.dispatchEvent(new CustomEvent('familyos:sync-changed',{detail:{accountId:this.accountId,familyId:this.familyId,state:this.engine.state}}))}
 setLiveState(state){if(this.engine.liveState===state)return;this.engine.liveState=state;this.notifyLocal();this.publishStatus()}
 openSocket(){
  if(!this.isLeader()||this.socket)return;if(!this.Socket){this.setLiveState('unavailable');return}
  try{
   const protocol=globalThis.location?.protocol==='https:'?'wss:':'ws:',host=globalThis.location?.host||'localhost';
   // Retrying is a transport detail: keep the last failure visible until open.
   if(!['reconnecting','unavailable'].includes(this.engine.liveState))this.setLiveState('connecting');const socket=new this.Socket(`${protocol}//${host}/ws/sync/${this.familyId}/`);this.socket=socket;
   socket.onopen=()=>{if(this.socket===socket&&this.isLeader()){socket.__familyosOpened=true;this.setLiveState('connected');this.runLeaderSync()}};
   socket.onmessage=e=>{try{const data=JSON.parse(e.data);if(data.type==='sync_available'&&String(data.family_id)===this.familyId)this.runLeaderSync()}catch{}};
   socket.onclose=()=>{if(this.socket!==socket)return;this.socket=null;if(this.isLeader()){this.setLiveState('reconnecting');if(socket.__familyosOpened||this.now()-this.lastProbe>=PROBE_MS)this.runLeaderSync()}};socket.onerror=()=>{if(this.socket===socket&&this.isLeader()){this.setLiveState('reconnecting');if(socket.__familyosOpened||this.now()-this.lastProbe>=PROBE_MS)this.runLeaderSync()}};
  }catch{this.socket=null;this.setLiveState('unavailable')}
 }
 stepDown(){this.leader=false;this.timers.clearTimeout?.(this.syncTimer);try{this.socket?.close?.()}catch{}this.socket=null}
 stop(){
  if(this.stopped)return;this.stopped=true;this.timers.clearInterval?.(this.timer);this.timers.clearTimeout?.(this.syncTimer);this.stepDown();
  try{const current=parse(this.storage?.getItem?.(this.key));if(current?.owner===this.id){this.storage.removeItem(this.key);this.storage.removeItem(this.requestKey);this.storage.removeItem(this.stateKey)}}catch{}
  try{this.channel?.close?.()}catch{}globalThis.removeEventListener?.('storage',this.storageHandler);
 }
}

export function routeEngineThrough(coordinator,engine){
 if(engine.__liveCoordinator===coordinator)return;
 if(!engine.__directSync){
  engine.__directSync=engine.sync.bind(engine);
  engine.__directSchedule=engine.schedule.bind(engine);
  engine.sync=(options={})=>{
   const active=engine.__liveCoordinator;
   if(!active||options.leader||active.isLeader())return engine.__directSync();
   active.requestSync();return Promise.resolve();
  };
  engine.schedule=()=>{
   const active=engine.__liveCoordinator;
   if(active)return active.requestSync();
   return engine.__directSchedule();
  };
 }
 engine.__liveCoordinator=coordinator;
}

export function ensureLiveCoordinator(engine,{accountId,familyId}={}){
 const key=`${accountId}:${familyId}`;let coordinator=coordinators.get(key);
 if(!coordinator){coordinator=new LiveSyncCoordinator({accountId,familyId,engine}).start();coordinators.set(key,coordinator)}
 routeEngineThrough(coordinator,engine);return coordinator;
}
export function stopLiveAccount(accountId){for(const [key,value] of coordinators)if(key.startsWith(`${accountId}:`)){value.stop();value.engine.__liveCoordinator=null;coordinators.delete(key)}}
