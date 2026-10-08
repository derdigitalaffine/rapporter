const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const SESSION_MARKER='famuhle-session';
const jsonHeaders = () => ({'Content-Type':'application/json'});

export function markAuthenticated(value=true){
 if(value)localStorage.setItem(SESSION_MARKER,'1');else localStorage.removeItem(SESSION_MARKER);
}
export async function login(username,password){
 const response=await fetch(`${API_BASE}/auth/login/`,{method:'POST',credentials:'include',headers:jsonHeaders(),body:JSON.stringify({username,password})});
 if(!response.ok)throw new Error('login_failed');
 markAuthenticated(true);return response.json();
}
export function logout(){
 markAuthenticated(false);
 fetch(`${API_BASE}/auth/logout/`,{method:'POST',credentials:'include',headers:jsonHeaders()}).catch(()=>{});
}
export function isAuthenticated(){return localStorage.getItem(SESSION_MARKER)==='1'}
export async function checkSession(){
 const response=await fetch(`${API_BASE}/auth/session/`,{credentials:'include'});
 const ok=response.ok;if(ok)markAuthenticated(true);else markAuthenticated(false);return ok;
}
async function refreshAccess(){
 const response=await fetch(`${API_BASE}/auth/refresh/`,{method:'POST',credentials:'include',headers:jsonHeaders()});
 if(!response.ok){markAuthenticated(false);return false}
 markAuthenticated(true);return true;
}
async function request(path,options={}){
 return fetch(`${API_BASE}${path}`,{...options,credentials:'include',headers:{...jsonHeaders(),...(options.headers||{})}})
}
export async function api(path,options={}){
 let response=await request(path,options);
 if(response.status===401&&await refreshAccess())response=await request(path,options);
 if(response.status===401){markAuthenticated(false);throw new Error('unauthorized')}
 if(!response.ok){let detail='';try{detail=(await response.json()).detail||''}catch{}throw new Error(detail||`api_${response.status}`)}
 if(response.status===204)return null;return response.json();
}
