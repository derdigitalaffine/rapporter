const DB_NAME='famuhle-private-v1';
const STORE='loyalty-card-sync';
const VERSION=1;

function openDb(){
 return new Promise((resolve,reject)=>{
  if(!('indexedDB'in window)){reject(new Error('indexeddb_unavailable'));return}
  const request=indexedDB.open(DB_NAME,VERSION);
  request.onupgradeneeded=()=>{const db=request.result;if(!db.objectStoreNames.contains(STORE))db.createObjectStore(STORE,{keyPath:'family'})};
  request.onsuccess=()=>resolve(request.result);
  request.onerror=()=>reject(request.error||new Error('indexeddb_failed'));
 });
}

export async function loadOfflineCards(familyId){
 if(!familyId)return[];
 try{
  const db=await openDb();
  const result=await new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readonly');const req=tx.objectStore(STORE).get(String(familyId));req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)});
  db.close();
  return Array.isArray(result?.cards)?result.cards:[];
 }catch{return[]}
}

export async function replaceOfflineCards(familyId,cards){
 if(!familyId)return;
 try{
  const db=await openDb();
  await new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).put({family:String(familyId),cards:Array.isArray(cards)?cards:[],syncedAt:new Date().toISOString()});tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error)});
  db.close();
 }catch{}
}
