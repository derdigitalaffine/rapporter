const API_BASE = import.meta.env.VITE_API_BASE || '/api';

async function post(path, payload, locale) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'omit',
    headers: {
      'Content-Type': 'application/json',
      'Accept-Language': String(locale || '').startsWith('en') ? 'en' : 'de',
    },
    body: JSON.stringify(payload),
  });
  let data = null;
  try { data = await response.json(); } catch {}
  if (!response.ok) {
    const error = new Error(data?.detail || `api_${response.status}`);
    error.status = response.status;
    error.code = data?.code;
    error.payload = data;
    throw error;
  }
  return data;
}

export function requestPasswordReset(email, locale) {
  return post('/auth/password-reset/request/', {email: String(email || '').trim()}, locale);
}

export function confirmPasswordReset(uid, token, password, locale) {
  return post('/auth/password-reset/confirm/', {uid, token, password}, locale);
}
