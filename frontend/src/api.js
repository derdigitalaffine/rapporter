const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const jsonHeaders = () => ({'Content-Type':'application/json'});
const authHeaders = () => ({...jsonHeaders(),...(localStorage.getItem('famuhle-access')?{Authorization:`Bearer ${localStorage.getItem('famuhle-access')}`}:{})});

export function storeTokens(data){
 if(data?.access)localStorage.setItem('famuhle-access',data.access);
 if(data?.refresh)localStorage.setItem('famuhle-refresh',data.refresh);
 return data;
}
export async function login(username,password){
 const response=await fetch(`${API_BASE}/auth/token/`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({username,password})});
 if(!response.ok)throw new Error('login_failed');
 return storeTokens(await response.json());
}
export function logout(){localStorage.removeItem('famuhle-access');localStorage.removeItem('famuhle-refresh')}
export function isAuthenticated(){return Boolean(localStorage.getItem('famuhle-access')||localStorage.getItem('famuhle-refresh'))}
async function refreshAccess(){
 const refresh=localStorage.getItem('famuhle-refresh');if(!refresh)return false;
 const response=await fetch(`${API_BASE}/auth/token/refresh/`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({refresh})});
 if(!response.ok){logout();return false}
 const data=await response.json();storeTokens(data);return true;
}
async function request(path,options={}){return fetch(`${API_BASE}${path}`,{...options,headers:{...authHeaders(),...(options.headers||{})}})}
export async function api(path,options={}){
 let response=await request(path,options);
 if(response.status===401&&await refreshAccess())response=await request(path,options);
 if(response.status===401){logout();throw new Error('unauthorized')}
 if(!response.ok){let detail='';try{detail=(await response.json()).detail||''}catch{}throw new Error(detail||`api_${response.status}`)}
 if(response.status===204)return null;return response.json();
}
