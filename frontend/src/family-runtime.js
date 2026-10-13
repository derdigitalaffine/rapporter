const snapshots=new Map();
const MODULE_PATHS={baby:'/baby/module/',pets:'/pets/module/'};

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

export function clearFamilyModuleRuntime(familyId){
 if(familyId==null){snapshots.clear();return}
 snapshots.delete(key(familyId));
}

export function invalidateFamilyModuleRuntimeForPath(path){
 const url=requestUrl(path);if(!url)return;
 if(url.pathname.startsWith('/baby/')||url.pathname.startsWith('/pets/'))snapshots.clear();
}
