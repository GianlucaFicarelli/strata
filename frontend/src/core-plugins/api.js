/**
 * Core API fetch wrappers.
 *
 * All requests inject the bearer token from localStorage when present.
 * Secret fields are sent as "********" to preserve existing values when unchanged.
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
  const res = await fetch('/api/storage/backends', { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listDir(path = '/', backend) {
  const res = await fetch(`${BASE}/list${qs({ path, backend })}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteEntry(path, backend) {
  const res = await fetch(`${BASE}/delete${qs({ path, backend })}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function makeDir(path, backend) {
  const res = await fetch(`${BASE}/mkdir${qs({ path, backend })}`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function moveEntry(src, dst, backend) {
  const res = await fetch(`${BASE}/move${qs({ backend })}`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ src, dst }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

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
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Admin storage API ─────────────────────────────────────────────────────────

export async function listStorageTemplates() {
  const res = await fetch('/api/admin/storage/templates', { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listAdminInstances() {
  const res = await fetch('/api/admin/storage/instances', { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createAdminInstance(data) {
  const res = await fetch('/api/admin/storage/instances', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateAdminInstance(id, data) {
  const res = await fetch(`/api/admin/storage/instances/${id}`, {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteAdminInstance(id) {
  const res = await fetch(`/api/admin/storage/instances/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
}

// ── User self-service storage API ────────────────────────────────────────────

export async function listUserInstances() {
  const res = await fetch('/api/storage/instances', { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getUserInstanceConfig(instanceId) {
  const res = await fetch(`/api/storage/instances/${instanceId}/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateUserInstanceConfig(instanceId, data) {
  const res = await fetch(`/api/storage/instances/${instanceId}/me`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
