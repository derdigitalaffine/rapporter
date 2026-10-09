import {loadFamilyShell,offlineApiFallback,saveFamilyShell,saveShoppingSnapshot} from './offline-store';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const SESSION_MARKER='famuhle-session';
const SESSION_EXPIRED_EVENT='famuhle:session-expired';
const jsonHeaders = () => ({'Content-Type':'application/json'});
let refreshPromise=null;
let sessionExpiredSent=false;

export function markAuthenticated(value=true){
 if(value)localStorage.setItem(SESSION_MARKER,'1');else localStorage.removeItem(SESSION_MARKER);
}
function resetSessionExpiry(){sessionExpiredSent=false}
function notifySessionExpired(){
 markAuthenticated(false);
 if(sessionExpiredSent)return;
 sessionExpiredSent=true;
 window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
}
export async function login(username,password){
 const response=await fetch(`${API_BASE}/auth/login/`,{method:'POST',credentials:'include',headers:jsonHeaders(),body:JSON.stringify({username,password})});
 if(!response.ok)throw new Error('login_failed');
 markAuthenticated(true);resetSessionExpiry();return response.json();
}
export function logout(){
 markAuthenticated(false);resetSessionExpiry();
 fetch(`${API_BASE}/auth/logout/`,{method:'POST',credentials:'include',headers:jsonHeaders()}).catch(()=>{});
}
export function isAuthenticated(){return localStorage.getItem(SESSION_MARKER)==='1'}
export async function checkSession(){
 const response=await fetch(`${API_BASE}/auth/session/`,{credentials:'include'});
 const ok=response.ok;if(ok){markAuthenticated(true);resetSessionExpiry()}else markAuthenticated(false);return ok;
}
async function refreshAccess(){
 if(!refreshPromise){
  refreshPromise=fetch(`${API_BASE}/auth/refresh/`,{method:'POST',credentials:'include',headers:jsonHeaders()})
   .then(response=>{if(!response.ok){markAuthenticated(false);return false}markAuthenticated(true);resetSessionExpiry();return true})
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
  const fallback=await offlineApiFallback(path,options).catch(()=>({found:false}));
  if(fallback.found)return {fallback:fallback.value};
  throw error;
 }
}
async function rememberOfflineData(path,data,options={}){
 const method=(options.method||'GET').toUpperCase();if(method!=='GET')return;
 try{
  if(path==='/families/'&&Array.isArray(data)){await saveFamilyShell(data);return}
  if(path==='/shopping-lists/'&&Array.isArray(data)){
   const familyId=data[0]?.family||(await loadFamilyShell())?.[0]?.id;
   if(familyId)await saveShoppingSnapshot(familyId,data);
  }
 }catch{}
}
export async function api(path,options={}){
 let result=await requestOrOffline(path,options);
 if('fallback' in result)return result.fallback;
 let response=result.response;
 if(response.status===401&&await refreshAccess()){
  result=await requestOrOffline(path,options);if('fallback' in result)return result.fallback;response=result.response;
 }
 if(response.status===401){notifySessionExpired();throw new Error('unauthorized')}
 if(!response.ok){let detail='';try{detail=(await response.json()).detail||''}catch{}throw new Error(detail||`api_${response.status}`)}
 if(response.status===204)return null;
 const data=await response.json();await rememberOfflineData(path,data,options);return data;
}
