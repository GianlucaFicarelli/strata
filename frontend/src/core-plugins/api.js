/**
 * Core API fetch wrappers.
 *
 * All requests include `credentials: 'include'` so the browser sends the
 * HttpOnly `strata_session` cookie automatically.  This is required when the
 * Vite dev server (localhost:5173) makes cross-origin requests to FastAPI
 * (localhost:8000).  It is a no-op in production where both share one origin.
 *
 * No Authorization header is injected — authentication is handled entirely
 * by the session cookie.  There is no token in JS memory or localStorage.
 *
 * Download flow
 * -------------
 * Plain <a href> or window.open cannot send cookies cross-origin, so downloads
 * use a two-step approach:
 *   1. Call getDownloadToken(backend) → short-lived HMAC token from the server.
 *   2. Pass the token as ?token= in the download URL.
 * The token is valid for STRATA_DOWNLOAD_TOKEN_TTL_SECONDS (default 5 min).
 */

const BASE = '/api/files';

function qs(params) {
  return `?${new URLSearchParams(params).toString()}`;
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, { credentials: 'include', ...options });
  if (!res.ok) throw new Error(await res.text());
  return res;
}

function jsonOpts(method, data) {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  };
}

// ── File API ──────────────────────────────────────────────────────────────────

export async function listBackends() {
  const res = await apiFetch('/api/storage/backends');
  return res.json();
}

export async function listDir(path = '/', backend) {
  const res = await apiFetch(`${BASE}/list${qs({ path, backend })}`);
  return res.json();
}

export async function deleteEntry(path, backend) {
  const res = await apiFetch(`${BASE}/delete${qs({ path, backend })}`, { method: 'DELETE' });
  return res.json();
}

export async function makeDir(path, backend) {
  const res = await apiFetch(`${BASE}/mkdir${qs({ path, backend })}`, { method: 'POST' });
  return res.json();
}

export async function moveEntry(src, dst, backend) {
  const res = await apiFetch(`${BASE}/move${qs({ backend })}`, jsonOpts('POST', { src, dst }));
  return res.json();
}

export async function uploadFile(path, file, backend) {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch(`${BASE}/upload${qs({ path, backend })}`, {
    method: 'POST',
    body: form,
  });
  return res.json();
}

/**
 * Fetch a short-lived HMAC download token for the given backend.
 *
 * @param {string} backend - core_storage_instances UUID.
 * @returns {Promise<{token: string, expires_in: number}>}
 */
export async function getDownloadToken(backend) {
  const res = await apiFetch(`${BASE}/download-token${qs({ backend })}`);
  return res.json();
}

/**
 * Build a download URL for a file.
 *
 * Fetches a short-lived HMAC token first, then constructs the URL.
 * The token is embedded as ?token= so the link works as a plain <a href>.
 *
 * @param {string} path - Backend-relative file path.
 * @param {string} backend - core_storage_instances UUID.
 * @returns {Promise<string>} Fully-formed download URL.
 */
export async function downloadUrl(path, backend) {
  const { token } = await getDownloadToken(backend);
  return `${BASE}/download${qs({ path, token })}`;
}

// ── Admin storage API ─────────────────────────────────────────────────────────

export async function listStorageTemplates() {
  const res = await apiFetch('/api/admin/storage/templates');
  return res.json();
}

export async function listAdminInstances() {
  const res = await apiFetch('/api/admin/storage/instances');
  return res.json();
}

export async function createAdminInstance(data) {
  const res = await apiFetch('/api/admin/storage/instances', jsonOpts('POST', data));
  return res.json();
}

export async function updateAdminInstance(id, data) {
  const res = await apiFetch(`/api/admin/storage/instances/${id}`, jsonOpts('PUT', data));
  return res.json();
}

export async function deleteAdminInstance(id) {
  await apiFetch(`/api/admin/storage/instances/${id}`, { method: 'DELETE' });
}

// ── User self-service storage API ────────────────────────────────────────────

export async function listUserInstances() {
  const res = await apiFetch('/api/storage/instances');
  return res.json();
}

export async function getUserInstanceConfig(instanceId) {
  const res = await apiFetch(`/api/storage/instances/${instanceId}/me`);
  return res.json();
}

export async function updateUserInstanceConfig(instanceId, data) {
  const res = await apiFetch(`/api/storage/instances/${instanceId}/me`, jsonOpts('PATCH', data));
  return res.json();
}
