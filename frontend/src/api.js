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
 return fetch(`${API_BASE}${path}`,{...options,credentials:'include',headers:{...jsonHeaders(),...(options.headers||{})}})
}
export async function api(path,options={}){
 let response=await request(path,options);
 if(response.status===401&&await refreshAccess())response=await request(path,options);
 if(response.status===401){notifySessionExpired();throw new Error('unauthorized')}
 if(!response.ok){let detail='';try{detail=(await response.json()).detail||''}catch{}throw new Error(detail||`api_${response.status}`)}
 if(response.status===204)return null;return response.json();
}
