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
