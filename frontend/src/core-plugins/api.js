/**
 * Core API fetch wrappers.
 *
 * All requests:
 * - Inject the Bearer access token from localStorage via the Authorization header.
 * - Include credentials: 'include' so the browser sends the HttpOnly
 *   refresh-token cookie on every request. This is required for the Vite dev
 *   server (cross-origin to FastAPI) and is a no-op in production where both
 *   are served from the same origin.
 *
 * Secret fields are sent as "********" to preserve existing encrypted values
 * when unchanged (the backend treats the sentinel as "keep existing").
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

function jsonHeaders() {
  return { 'Content-Type': 'application/json', ...authHeaders() };
}

function qs(params) {
  return `?${new URLSearchParams(params).toString()}`;
}

// ── File API ──────────────────────────────────────────────────────────────────

export async function listBackends() {
  const res = await fetch('/api/storage/backends', {
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listDir(path = '/', backend) {
  const res = await fetch(`${BASE}/list${qs({ path, backend })}`, {
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteEntry(path, backend) {
  const res = await fetch(`${BASE}/delete${qs({ path, backend })}`, {
    method: 'DELETE',
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function makeDir(path, backend) {
  const res = await fetch(`${BASE}/mkdir${qs({ path, backend })}`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function moveEntry(src, dst, backend) {
  const res = await fetch(`${BASE}/move${qs({ backend })}`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ src, dst }),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * Returns a URL for direct file download.
 * Downloads use a plain <a href> or window.open — no fetch(), so credentials
 * cannot be injected.  The access token is passed as a query param instead.
 * The refresh token cookie is not needed here (it's scoped to /api/plugins/auth_jwt/*).
 */
export function downloadUrl(path, backend) {
  const token = getToken();
  const params = { path, backend };
  if (token) params.token = token;
  return `${BASE}/download${qs(params)}`;
}

export async function uploadFile(path, file, backend) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/upload${qs({ path, backend })}`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Admin storage API ─────────────────────────────────────────────────────────

export async function listStorageTemplates() {
  const res = await fetch('/api/admin/storage/templates', {
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listAdminInstances() {
  const res = await fetch('/api/admin/storage/instances', {
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createAdminInstance(data) {
  const res = await fetch('/api/admin/storage/instances', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateAdminInstance(id, data) {
  const res = await fetch(`/api/admin/storage/instances/${id}`, {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteAdminInstance(id) {
  const res = await fetch(`/api/admin/storage/instances/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
}

// ── User self-service storage API ────────────────────────────────────────────

export async function listUserInstances() {
  const res = await fetch('/api/storage/instances', {
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getUserInstanceConfig(instanceId) {
  const res = await fetch(`/api/storage/instances/${instanceId}/me`, {
    headers: authHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateUserInstanceConfig(instanceId, data) {
  const res = await fetch(`/api/storage/instances/${instanceId}/me`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
