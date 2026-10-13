const snapshots=new Map();
const MODULE_PATHS={baby:'/baby/module/',pets:'/pets/module/'};
const BOOTSTRAP_PATHS=new Set(['/auth/session/','/inbox/']);
const BOOTSTRAP_REUSE_MS=5000;
const bootstrapSnapshots=new Map();

function key(familyId){return String(familyId??'')}
function requestUrl(path){try{return new URL(path,'https://familyos.local')}catch{return null}}
function moduleForPath(path){
 const url=requestUrl(path);if(!url)return null;
 return Object.entries(MODULE_PATHS).find(([,pathname])=>url.pathname===pathname)?.[0]||null;
}

export function readFamilyModuleRuntime(familyId){
 const snapshot=snapshots.get(key(familyId));
 return snapshot?{...snapshot}:null;
}

export function rememberFamilyModuleRuntime(path,data){
 const url=requestUrl(path),module=moduleForPath(path),familyId=url?.searchParams.get('family');
 if(!module||!familyId)return;
 const current=snapshots.get(key(familyId))||{};
 snapshots.set(key(familyId),{...current,[module]:data});
}

export function rememberBootstrapRuntime(path,data){
 const url=requestUrl(path);if(!url||!BOOTSTRAP_PATHS.has(url.pathname))return;
 bootstrapSnapshots.set(url.pathname,{data,expiresAt:Date.now()+BOOTSTRAP_REUSE_MS});
}

export function takeBootstrapRuntime(path){
 const url=requestUrl(path);if(!url||!BOOTSTRAP_PATHS.has(url.pathname))return {found:false};
 const snapshot=bootstrapSnapshots.get(url.pathname);bootstrapSnapshots.delete(url.pathname);
 if(!snapshot||snapshot.expiresAt<Date.now())return {found:false};
 return {found:true,data:snapshot.data};
}

export function clearBootstrapRuntime(){bootstrapSnapshots.clear()}

export function clearFamilyModuleRuntime(familyId){
 if(familyId==null){snapshots.clear();return}
 snapshots.delete(key(familyId));
}

export function invalidateFamilyModuleRuntimeForPath(path){
 const url=requestUrl(path);if(!url)return;
 if(url.pathname.startsWith('/baby/')||url.pathname.startsWith('/pets/'))snapshots.clear();
}
