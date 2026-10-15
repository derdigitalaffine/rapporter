const coordinators=new Map();
const LEASE_MS=5000, HEARTBEAT_MS=2000;
const parse=value=>{try{return JSON.parse(value||'null')}catch{return null}};

export class LiveSyncCoordinator{
 constructor({accountId,familyId,engine,storage=globalThis.localStorage,Channel=globalThis.BroadcastChannel,Socket=globalThis.WebSocket,now=()=>Date.now(),timers=globalThis}={}){
  Object.assign(this,{accountId:String(accountId),familyId:String(familyId),engine,storage,Channel,Socket,now,timers});
  this.id=globalThis.crypto?.randomUUID?.()||`${Math.random()}`;this.key=`familyos-sync-leader:${this.accountId}:${this.familyId}`;this.requestKey=`${this.key}:request`;this.channelName=`familyos-sync:${this.accountId}:${this.familyId}`;this.leader=false;this.stopped=false;this.socket=null;
 }
 isLeader(){return this.leader&&!this.stopped}
 start(){
  if(this.stopped)return this;this.stopped=false;
  if(this.Channel){try{this.channel=new this.Channel(this.channelName);this.channel.onmessage=e=>{if(e.data?.type==='sync-request'&&this.isLeader())this.runLeaderSync()}}catch{}}
  this.storageHandler=e=>{if(e.key===this.requestKey&&this.isLeader())this.runLeaderSync();if(e.key===this.key)this.checkLease()};
  globalThis.addEventListener?.('storage',this.storageHandler);this.checkLease();this.timer=this.timers.setInterval?.(()=>this.checkLease(),HEARTBEAT_MS);return this;
 }
 checkLease(){
  if(this.stopped)return;const current=parse(this.storage?.getItem?.(this.key)),time=this.now();
  if(this.leader){if(current&&current.owner!==this.id&&current.expires>time){this.stepDown();return}this.writeLease();return}
  if(!current||current.expires<=time||current.owner===this.id){this.leader=true;this.writeLease();this.openSocket();this.runLeaderSync()}
 }
 writeLease(){try{this.storage?.setItem?.(this.key,JSON.stringify({owner:this.id,expires:this.now()+LEASE_MS}))}catch{}}
 requestSync(){
  if(this.stopped)return;if(this.isLeader()){clearTimeout(this.syncTimer);this.syncTimer=this.timers.setTimeout?.(()=>this.runLeaderSync(),30);return}
  try{this.channel?.postMessage?.({type:'sync-request'})}catch{}
  try{this.storage?.setItem?.(this.requestKey,JSON.stringify({from:this.id,at:this.now()}))}catch{}
  this.checkLease();
 }
 runLeaderSync(){if(this.isLeader())this.engine.sync({leader:true}).catch(()=>{})}
 openSocket(){
  if(!this.Socket||!this.isLeader()||this.socket)return;
  try{
   const protocol=globalThis.location?.protocol==='https:'?'wss:':'ws:',host=globalThis.location?.host||'localhost';
   const socket=new this.Socket(`${protocol}//${host}/ws/sync/${this.familyId}/`);this.socket=socket;
   socket.onmessage=e=>{try{const data=JSON.parse(e.data);if(data.type==='sync_available'&&String(data.family_id)===this.familyId)this.runLeaderSync()}catch{}};
   socket.onclose=()=>{if(this.socket===socket)this.socket=null};socket.onerror=()=>{};
  }catch{this.socket=null}
 }
 stepDown(){this.leader=false;clearTimeout(this.syncTimer);try{this.socket?.close?.()}catch{}this.socket=null}
 stop(){
  if(this.stopped)return;this.stopped=true;clearInterval(this.timer);clearTimeout(this.syncTimer);this.stepDown();
  try{const current=parse(this.storage?.getItem?.(this.key));if(current?.owner===this.id)this.storage.removeItem(this.key)}catch{}
  try{this.channel?.close?.()}catch{}globalThis.removeEventListener?.('storage',this.storageHandler);
 }
}

export function ensureLiveCoordinator(engine,{accountId,familyId}={}){
 const key=`${accountId}:${familyId}`;let coordinator=coordinators.get(key);
 if(!coordinator){coordinator=new LiveSyncCoordinator({accountId,familyId,engine}).start();coordinators.set(key,coordinator)}
 engine.setCoordinator?.(coordinator);return coordinator;
}
export function stopLiveAccount(accountId){for(const [key,value] of coordinators)if(key.startsWith(`${accountId}:`)){value.stop();coordinators.delete(key)}}
