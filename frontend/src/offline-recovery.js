export const BACKGROUND_SYNC_TAG='familyos-outbox-v1';

// A worker wake-up only nudges authenticated window clients. It never stores
// tokens, guesses an account, sends domain data or acknowledges an outbox entry.
export async function requestBackgroundSync(serviceWorker=globalThis.navigator?.serviceWorker){
 try{
  if(!serviceWorker)return false;
  const registration=await serviceWorker.ready;
  if(!registration.sync?.register)return false;
  await registration.sync.register(BACKGROUND_SYNC_TAG);return true;
 }catch{return false}
}

export async function storageDiagnostics(storage=globalThis.navigator?.storage){
 const result={supported:Boolean(storage),persistent:null,usage:null,quota:null,lowSpace:false};
 if(!storage)return result;
 const [persisted,estimate]=await Promise.allSettled([
  storage.persisted?.(),storage.estimate?.(),
 ]);
 if(persisted.status==='fulfilled'&&typeof persisted.value==='boolean')result.persistent=persisted.value;
 if(estimate.status==='fulfilled'){
  const {usage,quota}=estimate.value||{};
  if(Number.isFinite(usage)&&usage>=0)result.usage=usage;
  if(Number.isFinite(quota)&&quota>0)result.quota=quota;
  result.lowSpace=result.quota!==null&&result.usage!==null&&result.usage/result.quota>=.9;
 }
 return result;
}
