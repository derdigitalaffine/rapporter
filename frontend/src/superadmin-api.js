const API_BASE=import.meta.env.VITE_API_BASE||'/api';
export const ADMIN_SESSION_EXPIRED_EVENT='familyos-admin:session-expired';
const jsonHeaders=()=>({'Content-Type':'application/json'});
let refreshPromise=null;
let expiredSent=false;

function errorMessage(payload){
  if(!payload||typeof payload!=='object')return'';
  if(typeof payload.detail==='string')return payload.detail;
  for(const value of Object.values(payload)){
    if(typeof value==='string')return value;
    if(Array.isArray(value)&&typeof value[0]==='string')return value[0];
    if(value&&typeof value==='object'){const nested=errorMessage(value);if(nested)return nested}
  }
  return'';
}
function apiError(response,payload){const error=new Error(errorMessage(payload)||`api_${response.status}`);error.status=response.status;error.code=payload?.code;error.payload=payload;return error}
function notifyExpired(){if(expiredSent)return;expiredSent=true;window.dispatchEvent(new CustomEvent(ADMIN_SESSION_EXPIRED_EVENT))}
function resetExpired(){expiredSent=false}
async function request(path,options={}){const multipart=typeof FormData!=='undefined'&&options.body instanceof FormData;const headers=multipart?{...(options.headers||{})}:{...jsonHeaders(),...(options.headers||{})};return fetch(`${API_BASE}/superadmin${path}`,{...options,credentials:'include',headers})}
async function refreshAdmin(){
  if(!refreshPromise){
    refreshPromise=request('/auth/refresh/',{method:'POST'})
      .then(response=>{if(!response.ok)return false;resetExpired();return true})
      .catch(()=>false)
      .finally(()=>{refreshPromise=null});
  }
  return refreshPromise;
}
async function parseResponse(response){if(response.status===204)return null;let payload=null;try{payload=await response.json()}catch{}if(!response.ok)throw apiError(response,payload);return payload}

export async function adminLogin(identifier,password){const response=await request('/auth/login/',{method:'POST',body:JSON.stringify({identifier:String(identifier||'').trim(),password})});const data=await parseResponse(response);resetExpired();return data}
export async function adminLogout(){try{await request('/auth/logout/',{method:'POST'})}finally{resetExpired()}}
export async function adminSession(){const response=await request('/auth/session/');if(!response.ok)throw apiError(response,null);resetExpired();return response.json()}
export async function adminApi(path,options={}){
  let response=await request(path,options);
  if(response.status===401&&await refreshAdmin())response=await request(path,options);
  if(response.status===401){notifyExpired();throw apiError(response,null)}
  return parseResponse(response);
}
