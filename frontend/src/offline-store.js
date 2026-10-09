const DB_NAME='famuhle-offline-v1';
const DB_VERSION=1;
const SNAPSHOTS='shoppingSnapshots';
const MUTATIONS='shoppingMutations';
const SHELL='appShell';

function openDb(){
  return new Promise((resolve,reject)=>{
    if(typeof indexedDB==='undefined'){reject(new Error('indexeddb_unavailable'));return}
    const request=indexedDB.open(DB_NAME,DB_VERSION);
    request.onupgradeneeded=()=>{
      const db=request.result;
      if(!db.objectStoreNames.contains(SNAPSHOTS))db.createObjectStore(SNAPSHOTS,{keyPath:'familyId'});
      if(!db.objectStoreNames.contains(MUTATIONS)){
        const store=db.createObjectStore(MUTATIONS,{keyPath:'id'});
        store.createIndex('familyId','familyId',{unique:false});
      }
      if(!db.objectStoreNames.contains(SHELL))db.createObjectStore(SHELL,{keyPath:'key'});
    };
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error||new Error('indexeddb_open_failed'));
  });
}

async function tx(storeName,mode,work){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const transaction=db.transaction(storeName,mode);const store=transaction.objectStore(storeName);
    let result;
    try{result=work(store)}catch(error){db.close();reject(error);return}
    transaction.oncomplete=()=>{db.close();resolve(result)};
    transaction.onerror=()=>{db.close();reject(transaction.error||new Error('indexeddb_transaction_failed'))};
    transaction.onabort=()=>{db.close();reject(transaction.error||new Error('indexeddb_transaction_aborted'))};
  });
}

function requestValue(request){return new Promise((resolve,reject)=>{request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)})}

export async function saveShoppingSnapshot(familyId,lists){if(!familyId)return;await tx(SNAPSHOTS,'readwrite',store=>store.put({familyId:String(familyId),lists,updatedAt:Date.now()}))}
export async function loadShoppingSnapshot(familyId){if(!familyId)return null;const db=await openDb();try{return await requestValue(db.transaction(SNAPSHOTS,'readonly').objectStore(SNAPSHOTS).get(String(familyId)))}finally{db.close()}}

export async function putShoppingMutation(mutation){await tx(MUTATIONS,'readwrite',store=>store.put(mutation));return mutation}
export async function deleteShoppingMutation(id){await tx(MUTATIONS,'readwrite',store=>store.delete(id))}
export async function listShoppingMutations(familyId){
  const db=await openDb();
  try{
    const store=db.transaction(MUTATIONS,'readonly').objectStore(MUTATIONS);const index=store.index('familyId');
    const rows=await requestValue(index.getAll(String(familyId)));
    return rows.sort((a,b)=>(a.createdAt||0)-(b.createdAt||0));
  }finally{db.close()}
}

export async function saveFamilyShell(families){
  const safe=(families||[]).map(f=>({id:f.id,name:f.name,slug:f.slug,locale:f.locale,timezone:f.timezone,memberships:[]}));
  await tx(SHELL,'readwrite',store=>store.put({key:'families',value:safe,updatedAt:Date.now()}));
}
export async function loadFamilyShell(){const db=await openDb();try{return (await requestValue(db.transaction(SHELL,'readonly').objectStore(SHELL).get('families')))?.value||null}finally{db.close()}}

export async function offlineApiFallback(path,options={}){
  const method=(options.method||'GET').toUpperCase();if(method!=='GET')return {found:false};
  if(path==='/families/'){const families=await loadFamilyShell();return families?{found:true,value:families}:{found:false}}
  if(path==='/inbox/'||path==='/automation-rules/')return {found:true,value:[]};
  if(path.startsWith('/shopping-lists/')){
    const families=await loadFamilyShell();const familyId=families?.[0]?.id;const snapshot=await loadShoppingSnapshot(familyId);return snapshot?{found:true,value:snapshot.lists}:{found:false};
  }
  if(path.startsWith('/dashboard/')){
    const query=path.includes('?')?new URLSearchParams(path.slice(path.indexOf('?')+1)):new URLSearchParams();
    const familyId=query.get('family')||(await loadFamilyShell())?.[0]?.id;const snapshot=await loadShoppingSnapshot(familyId);
    if(!snapshot)return {found:false};
    return {found:true,value:{tasks:[],task_lists:[],events:[],routines:[],shopping_lists:snapshot.lists,inbox_count:0,automation_count:0,offline_fallback:true}};
  }
  return {found:false};
}
