const MESSAGE_TIMEOUT_MS=5000;

function serviceWorkerTarget(){
 if(typeof navigator==='undefined'||!('serviceWorker' in navigator))return Promise.reject(new Error('share_target_unsupported'));
 return navigator.serviceWorker.ready.then(registration=>navigator.serviceWorker.controller||registration.active||registration.waiting).then(worker=>{
  if(!worker)throw new Error('share_target_unavailable');
  return worker;
 });
}

export async function shareTargetMessage(message,{timeout=MESSAGE_TIMEOUT_MS}={}){
 const worker=await serviceWorkerTarget();
 return new Promise((resolve,reject)=>{
  const channel=new MessageChannel();
  const timer=setTimeout(()=>{channel.port1.close();reject(new Error('share_target_timeout'))},timeout);
  channel.port1.onmessage=event=>{clearTimeout(timer);channel.port1.close();const payload=event.data||{};if(payload.ok===false){const error=new Error(payload.code||'share_target_failed');error.code=payload.code;reject(error);return}resolve(payload)};
  try{worker.postMessage(message,[channel.port2])}catch(error){clearTimeout(timer);channel.port1.close();reject(error)}
 });
}

export async function loadSharedBatch(batchId){
 const response=await shareTargetMessage({type:'share-target:get',batchId});
 return response.batch||null;
}

export function consumeSharedItem(batchId,itemId){return shareTargetMessage({type:'share-target:consume',batchId,itemId})}
export function discardSharedItem(batchId,itemId){return shareTargetMessage({type:'share-target:discard-item',batchId,itemId})}
export function discardSharedBatch(batchId){return shareTargetMessage({type:'share-target:discard-batch',batchId})}
export function cleanupSharedBatches(){return shareTargetMessage({type:'share-target:cleanup'})}

export function fileTitle(name=''){
 const trimmed=String(name||'').trim();
 if(!trimmed)return'Dokument';
 return trimmed.replace(/\.[^.]+$/,'').trim()||'Dokument';
}

export function allowedDocumentFile(file){
 return Boolean(file&&['application/pdf','image/jpeg','image/png','image/webp'].includes(file.type));
}

export function sharedItemToFile(item){
 if(!item?.blob)return null;
 if(typeof File!=='undefined'&&item.blob instanceof File)return item.blob;
 return new File([item.blob],item.name||'Dokument',{type:item.type||item.blob.type||'application/octet-stream',lastModified:Number(item.lastModified||Date.now())});
}
