const BASE = '/api/files';

function qs(params) {
  return '?' + new URLSearchParams(params).toString();
}

export async function listBackends() {
  const res = await fetch('/api/backends');
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listDir(path = '/', backend = 'local') {
  const res = await fetch(`${BASE}/list${qs({ path, backend })}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteEntry(path, backend = 'local') {
  const res = await fetch(`${BASE}/delete${qs({ path, backend })}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function makeDir(path, backend = 'local') {
  const res = await fetch(`${BASE}/mkdir${qs({ path, backend })}`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function moveEntry(src, dst, backend = 'local') {
  const res = await fetch(`${BASE}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src, dst, backend }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function downloadUrl(path, backend = 'local') {
  return `${BASE}/download${qs({ path, backend })}`;
}

export async function uploadFile(path, file, backend = 'local') {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/upload${qs({ path, backend })}`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
