export function syncStatus({online=true,state='idle',serverState='unknown',lastSyncAt=null,pending=0,conflicts=0,now=Date.now()}){
 if(!online||state==='offline')return 'offline';
 if(state==='auth-required'||serverState==='auth-required')return 'auth';
 if(serverState==='unreachable')return 'serverDown';
 if(conflicts)return 'attention';
 if(state==='synchronizing')return 'busy';
 if(pending||state==='retry')return 'retry';
 const stamp=Date.parse(lastSyncAt||'');
 if(state==='synced'&&serverState==='reachable'&&Number.isFinite(stamp)&&now-stamp<60000)return 'sync';
 return 'checking';
}

// Header health is deliberately independent of the short-lived busy state.
// A routine confirmed, empty-queue check must not flash a different label/color.
export function syncIndicator({online=true,state='idle',serverState='unknown',liveState='connecting',lastSyncAt=null,pending=0,conflicts=0,now=Date.now()}){
 if(!online||state==='offline')return 'offline';
 if(state==='auth-required'||serverState==='auth-required'||serverState==='unreachable')return 'error';
 if(pending||conflicts||state==='retry'||state==='action-required')return 'attention';
 const stamp=Date.parse(lastSyncAt||'');
 const confirmed=serverState==='reachable'&&Number.isFinite(stamp)&&now-stamp<60000;
 if(!confirmed)return 'checking';
 return liveState==='connected'?'ready':'attention';
}
export const SYNC_INDICATORS=Object.freeze({
 ready:{label:'ledReady',symbol:'✓'},attention:{label:'ledAttention',symbol:'!'},
 error:{label:'ledError',symbol:'!'},checking:{label:'ledChecking',symbol:'…'},offline:{label:'ledOffline',symbol:'–'}
});
