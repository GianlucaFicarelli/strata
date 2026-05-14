/**
 * Core file-API fetch wrappers.
 *
 * getToken()
 * ----------
 * All requests read the current bearer token from localStorage via
 * getToken().  This is the same key AuthContext writes to, so the token
 * is always up-to-date without any prop-drilling or context dependency in
 * this module.
 *
 * If no token is present the Authorization header is simply omitted, which
 * is correct for deployments without an auth plugin (OptionalCurrentUserDep
 * returns null on the backend and the request succeeds).
 */

const BASE = '/api/files';
const TOKEN_KEY = 'strata_token';

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function qs(params) {
  return '?' + new URLSearchParams(params).toString();
}

export async function listBackends() {
  const res = await fetch('/api/backends', { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listDir(path = '/', backend = 'storage_local') {
  const res = await fetch(`${BASE}/list${qs({ path, backend })}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteEntry(path, backend = 'storage_local') {
  const res = await fetch(`${BASE}/delete${qs({ path, backend })}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function makeDir(path, backend = 'storage_local') {
  const res = await fetch(`${BASE}/mkdir${qs({ path, backend })}`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function moveEntry(src, dst, backend = 'storage_local') {
  const res = await fetch(`${BASE}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ src, dst, backend }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function downloadUrl(path, backend = 'storage_local') {
  // Download URLs include the token as a query param since we can't set
  // headers on window.open() / anchor clicks.
  const token = getToken();
  const params = { path, backend };
  if (token) params.token = token;
  return `${BASE}/download${qs(params)}`;
}

export async function uploadFile(path, file, backend = 'storage_local') {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/upload${qs({ path, backend })}`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
