import {api} from './api';

const DB_NAME='famuhle-shopping-offline';
const DB_VERSION=1;
const SNAPSHOTS='snapshots';
const QUEUE='queue';

function openDb(){
 return new Promise((resolve,reject)=>{
  const request=indexedDB.open(DB_NAME,DB_VERSION);
  request.onupgradeneeded=()=>{
   const db=request.result;
   if(!db.objectStoreNames.contains(SNAPSHOTS))db.createObjectStore(SNAPSHOTS,{keyPath:'familyId'});
   if(!db.objectStoreNames.contains(QUEUE)){
    const store=db.createObjectStore(QUEUE,{keyPath:'id'});
    store.createIndex('familyId','familyId',{unique:false});
   }
  };
  request.onsuccess=()=>resolve(request.result);
  request.onerror=()=>reject(request.error);
 });
}

function txRequest(store,method,...args){
 return new Promise((resolve,reject)=>{
  const request=store[method](...args);
  request.onsuccess=()=>resolve(request.result);
  request.onerror=()=>reject(request.error);
 });
}

async function withStore(name,mode,fn){
 const db=await openDb();
 try{
  const transaction=db.transaction(name,mode);
  const result=await fn(transaction.objectStore(name));
  await new Promise((resolve,reject)=>{transaction.oncomplete=resolve;transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error)});
  return result;
 }finally{db.close()}
}

export async function saveShoppingSnapshot(familyId,lists){
 if(!familyId)return;
 await withStore(SNAPSHOTS,'readwrite',store=>txRequest(store,'put',{familyId:String(familyId),lists,updatedAt:Date.now()}));
}

export async function loadShoppingSnapshot(familyId){
 if(!familyId)return null;
 return withStore(SNAPSHOTS,'readonly',async store=>(await txRequest(store,'get',String(familyId)))||null);
}

export async function listShoppingMutations(familyId){
 if(!familyId)return[];
 return withStore(QUEUE,'readonly',async store=>{
  const index=store.index('familyId');
  const rows=await txRequest(index,'getAll',String(familyId));
  return rows.sort((a,b)=>a.createdAt-b.createdAt);
 });
}

async function putMutation(row){return withStore(QUEUE,'readwrite',store=>txRequest(store,'put',row))}
async function deleteMutation(id){return withStore(QUEUE,'readwrite',store=>txRequest(store,'delete',id))}

export async function queueShoppingMutation(familyId,mutation){
 const family=String(familyId);
 const rows=await listShoppingMutations(family);
 const target=mutation.itemId||mutation.tempId||'';
 const existing=rows.find(row=>row.type===mutation.type&&(row.itemId||row.tempId||'')===target);
 if(existing&&['edit','checked','favorite'].includes(mutation.type)){
  const next={...existing,payload:{...(existing.payload||{}),...(mutation.payload||{})},attempts:0,lastError:''};
  await putMutation(next);return next;
 }
 const row={id:crypto.randomUUID(),familyId:family,createdAt:Date.now(),attempts:0,lastError:'',...mutation};
 await putMutation(row);return row;
}

export async function replaceQueuedTempId(familyId,tempId,realId){
 const rows=await listShoppingMutations(familyId);
 await Promise.all(rows.filter(row=>row.itemId===tempId).map(row=>putMutation({...row,itemId:String(realId)})));
}

export async function removeQueuedMutationsForItem(familyId,itemId,types=[]){
 const rows=await listShoppingMutations(familyId);
 const matches=rows.filter(row=>row.itemId===itemId&&(!types.length||types.includes(row.type)));
 await Promise.all(matches.map(row=>deleteMutation(row.id)));
}

async function executeMutation(row){
 if(row.type==='add'){
  return api('/smart/shopping/quick-add/',{method:'POST',body:JSON.stringify(row.payload)});
 }
 if(['edit','checked','favorite'].includes(row.type)){
  return api(`/shopping-items/${row.itemId}/`,{method:'PATCH',body:JSON.stringify(row.payload)});
 }
 throw new Error(`unsupported_shopping_mutation_${row.type}`);
}

export async function flushShoppingMutations(familyId,{onMapped}={}){
 if(!navigator.onLine)return {pending:(await listShoppingMutations(familyId)).length,failed:0};
 const rows=await listShoppingMutations(familyId);
 let failed=0;
 for(const row of rows){
  try{
   const result=await executeMutation(row);
   if(row.type==='add'&&row.tempId&&result?.id){
    await replaceQueuedTempId(familyId,row.tempId,result.id);
    await onMapped?.(row.tempId,result);
   }
   await deleteMutation(row.id);
  }catch(error){
   if(error?.message==='unauthorized')throw error;
   failed+=1;
   await putMutation({...row,attempts:(row.attempts||0)+1,lastError:error?.message||'sync_failed'});
   break;
  }
 }
 const pending=(await listShoppingMutations(familyId)).length;
 return {pending,failed};
}

export function optimisticId(){return `offline-${crypto.randomUUID()}`}
