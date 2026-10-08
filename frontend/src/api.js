const API_BASE = import.meta.env.VITE_API_BASE || '/api';

const authHeaders = () => ({ 'Content-Type': 'application/json', ...(localStorage.getItem('famuhle-access') ? { Authorization: `Bearer ${localStorage.getItem('famuhle-access')}` } : {}) });

export async function login(username, password) {
  const response = await fetch(`${API_BASE}/auth/token/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
  if (!response.ok) throw new Error('login_failed');
  const data = await response.json();
  localStorage.setItem('famuhle-access', data.access);
  localStorage.setItem('famuhle-refresh', data.refresh);
  return data;
}

export function logout() { localStorage.removeItem('famuhle-access'); localStorage.removeItem('famuhle-refresh'); }
export function isAuthenticated() { return Boolean(localStorage.getItem('famuhle-access')); }

export async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...authHeaders(), ...(options.headers || {}) } });
  if (response.status === 401) { logout(); throw new Error('unauthorized'); }
  if (!response.ok) throw new Error(`api_${response.status}`);
  if (response.status === 204) return null;
  return response.json();
}
