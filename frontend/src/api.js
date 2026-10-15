import {offlineTaskRequest} from './offline-tasks';
import {offlineShoppingRequest,offlineMetadata,rememberOfflineBootstrap,clearOfflineIdentity,setSyncTransport,offlineIdentity,offlineDashboard} from './offline-runtime';
import {clearBootstrapRuntime,clearFamilyModuleRuntime,invalidateFamilyModuleRuntimeForPath,rememberBootstrapRuntime,rememberFamilyModuleRuntime,takeBootstrapRuntime} from './family-runtime';
import {loadFamilyShell,offlineApiFallback,saveFamilyShell,saveShoppingSnapshot} from './offline-store';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const SESSION_MARKER='famuhle-session';
const SESSION_EXPIRED_EVENT='famuhle:session-expired';
export const AUTH_CHANGED_EVENT='famuhle:auth-changed';
const jsonHeaders = () => ({'Content-Type':'application/json'});
let refreshPromise=null;
let sessionExpiredSent=false;

export function markAuthenticated(value=true){
 if(value)localStorage.setItem(SESSION_MARKER,'1');else{localStorage.removeItem(SESSION_MARKER);clearFamilyModuleRuntime();clearBootstrapRuntime()}
 window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT,{detail:{authenticated:Boolean(value)}}));
}
function resetSessionExpiry(){sessionExpiredSent=false}
function notifySessionExpired(){
 if(offlineIdentity()){window.dispatchEvent(new CustomEvent('familyos:reauth-required'));return}
 markAuthenticated(false);
 if(sessionExpiredSent)return;
 sessionExpiredSent=true;
 window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
}
export async function login(identifier,password,{legacy=false}={}){
 const value=String(identifier||'').trim();
 const useLegacy=Boolean(legacy);
 const payload=useLegacy?{username:value,password,legacy:true}:{email:value,password};
 const response=await fetch(`${API_BASE}/auth/login/`,{method:'POST',credentials:'include',headers:jsonHeaders(),body:JSON.stringify(payload)});
 if(!response.ok)throw new Error('login_failed');
 markAuthenticated(true);resetSessionExpiry();return response.json();
}
export async function logout(){
 markAuthenticated(false);resetSessionExpiry();
 let cleanupError;try{await clearOfflineIdentity()}catch(error){cleanupError=error}
 fetch(`${API_BASE}/auth/logout/`,{method:'POST',credentials:'include',headers:jsonHeaders()}).catch(()=>{});
 if(cleanupError)throw cleanupError;
}
export function isAuthenticated(){return localStorage.getItem(SESSION_MARKER)==='1'}
export async function checkSession(){
 const response=await fetch(`${API_BASE}/auth/session/`,{credentials:'include'});
 const ok=response.ok;if(ok){markAuthenticated(true);resetSessionExpiry()}else markAuthenticated(false);return ok;
}
async function refreshAccess(){
 if(!refreshPromise){
  refreshPromise=fetch(`${API_BASE}/auth/refresh/`,{method:'POST',credentials:'include',headers:jsonHeaders()})
   .then(response=>{if(!response.ok){if(!offlineIdentity())markAuthenticated(false);return false}markAuthenticated(true);resetSessionExpiry();return true})
   .catch(()=>false)
   .finally(()=>{refreshPromise=null});
 }
 return refreshPromise;
}
async function request(path,options={}){
 const multipart=typeof FormData!=='undefined'&&options.body instanceof FormData;
 const headers=multipart?{...(options.headers||{})}:{...jsonHeaders(),...(options.headers||{})};
 return fetch(`${API_BASE}${path}`,{...options,credentials:'include',headers})
}
async function requestOrOffline(path,options={}){
 try{return {response:await request(path,options)}}catch(error){
  const scoped=offlineMetadata(path);if(scoped.handled)return {fallback:scoped.value};
  const dashboard=await offlineDashboard(path);if(dashboard.handled)return {fallback:dashboard.value};
  const fallback=await offlineApiFallback(path,options).catch(()=>({found:false}));
  if(fallback.found)return {fallback:fallback.value};
  throw error;
 }
}
async function rememberOfflineData(path,data,options={}){
 const method=(options.method||'GET').toUpperCase();if(method!=='GET')return;
 if(!isAuthenticated())return;
 await rememberOfflineBootstrap(path,data);
 try{
  if(offlineIdentity())return;
  if(path==='/families/'&&Array.isArray(data)){await saveFamilyShell(data);return}
  if(path==='/shopping-lists/'&&Array.isArray(data)){
   const familyId=data[0]?.family||(await loadFamilyShell())?.[0]?.id;
   if(familyId)await saveShoppingSnapshot(familyId,data);
  }
 }catch{}
}
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
function apiError(response,payload){
 const error=new Error(errorMessage(payload)||`api_${response.status}`);
 error.status=response.status;
 error.code=payload&&typeof payload==='object'?payload.code:undefined;
 error.payload=payload;
 return error;
}
export async function api(path,options={}){
 if(navigator.onLine===false){const scoped=offlineMetadata(path);if(scoped.handled)return scoped.value}
 const taskLocal=await offlineTaskRequest(path,options);if(taskLocal.handled){clearBootstrapRuntime();return taskLocal.value}
 const local=await offlineShoppingRequest(path,options);if(local.handled){clearBootstrapRuntime();return local.value}
 const method=(options.method||'GET').toUpperCase();
 if(method==='GET'){
  const runtime=takeBootstrapRuntime(path);if(runtime.found){await rememberOfflineBootstrap(path,runtime.data);return runtime.data}
 }else{
  invalidateFamilyModuleRuntimeForPath(path);clearBootstrapRuntime();
 }
 let result=await requestOrOffline(path,options);
 if('fallback' in result)return result.fallback;
 let response=result.response;
 if(response.status===401&&await refreshAccess()){
  result=await requestOrOffline(path,options);if('fallback' in result)return result.fallback;response=result.response;
 }
 if(response.status===401){const cached=offlineMetadata(path);if(cached.handled)return cached.value;notifySessionExpired();throw new Error('unauthorized')}
 if(!response.ok){let payload=null;try{payload=await response.json()}catch{}throw apiError(response,payload)}
 if(response.status===204)return null;
 const data=await response.json();
 if(method==='GET'){rememberFamilyModuleRuntime(path,data);rememberBootstrapRuntime(path,data)}
 await rememberOfflineData(path,data,options);return data;
}

export async function apiDownload(path){
 let response=await request(path,{method:'GET',headers:{Accept:'application/octet-stream'}});
 if(response.status===401&&await refreshAccess())response=await request(path,{method:'GET',headers:{Accept:'application/octet-stream'}});
 if(response.status===401){const cached=offlineMetadata(path);if(cached.handled)return cached.value;notifySessionExpired();throw new Error('unauthorized')}
 if(!response.ok){let payload=null;try{payload=await response.json()}catch{}throw apiError(response,payload)}
 const disposition=response.headers.get('Content-Disposition')||'';
 const match=disposition.match(/filename="?([^";]+)"?/i);
 return {blob:await response.blob(),filename:match?.[1]||'download'};
}

// Sync uses authenticated transport directly; it must never recurse through the
// domain adapter or treat an auth failure as a request to delete local work.
setSyncTransport(async(payload,signal)=>{
 let response=await request('/sync/',{method:'POST',body:JSON.stringify(payload),signal});
 if(response.status===401&&await refreshAccess())response=await request('/sync/',{method:'POST',body:JSON.stringify(payload),signal});
 if(!response.ok)throw Object.assign(new Error(`sync_${response.status}`),{status:response.status});
 return response.json();
});
