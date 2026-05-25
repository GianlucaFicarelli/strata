/**
 * Unit tests for src/core-plugins/api.js
 *
 * All tests mock global.fetch — no real network calls.
 * No localStorage usage expected anywhere in api.js.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  deleteEntry,
  downloadUrl,
  getDownloadToken,
  listBackends,
  listDir,
  makeDir,
  moveEntry,
  uploadFile,
} from '../../core-plugins/api';

const INSTANCE_ID = 'abc-123-uuid';

function mockFetch(json, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => json,
    text: async () => JSON.stringify(json),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

// ── Shared behaviour ──────────────────────────────────────────────────────────

describe('all requests', () => {
  it('include credentials: include (no Authorization header)', async () => {
    global.fetch = mockFetch([]);
    await listBackends();
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.credentials).toBe('include');
    // Must NOT inject an Authorization header
    expect(opts.headers?.Authorization).toBeUndefined();
  });
});

// ── listBackends ──────────────────────────────────────────────────────────────

describe('listBackends', () => {
  it('calls /api/storage/backends and returns json', async () => {
    const backends = [{ id: INSTANCE_ID, name: 'My Local', plugin_id: 'storage_local' }];
    global.fetch = mockFetch(backends);
    const result = await listBackends();
    expect(result).toEqual(backends);
    expect(global.fetch.mock.calls[0][0]).toBe('/api/storage/backends');
  });

  it('throws on non-ok response', async () => {
    global.fetch = mockFetch({ detail: 'error' }, false, 500);
    await expect(listBackends()).rejects.toThrow();
  });
});

// ── listDir ───────────────────────────────────────────────────────────────────

describe('listDir', () => {
  it('calls /api/files/list with correct query params', async () => {
    global.fetch = mockFetch([]);
    await listDir('/photos', INSTANCE_ID);
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('/api/files/list');
    expect(url).toContain('path=%2Fphotos');
    expect(url).toContain(`backend=${INSTANCE_ID}`);
  });

  it('uses "/" as the default path', async () => {
    global.fetch = mockFetch([]);
    await listDir(undefined, INSTANCE_ID);
    expect(global.fetch.mock.calls[0][0]).toContain('path=%2F');
  });
});

// ── deleteEntry ───────────────────────────────────────────────────────────────

describe('deleteEntry', () => {
  it('sends DELETE to /api/files/delete', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await deleteEntry('/old.txt', INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/delete');
    expect(opts.method).toBe('DELETE');
  });
});

// ── makeDir ───────────────────────────────────────────────────────────────────

describe('makeDir', () => {
  it('sends POST to /api/files/mkdir', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await makeDir('/newdir', INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/mkdir');
    expect(opts.method).toBe('POST');
  });
});

// ── moveEntry ─────────────────────────────────────────────────────────────────

describe('moveEntry', () => {
  it('sends POST with {src, dst} body', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await moveEntry('/a.txt', '/b.txt', INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain(`backend=${INSTANCE_ID}`);
    expect(opts.method).toBe('POST');
    const body = JSON.parse(opts.body);
    expect(body).toEqual({ src: '/a.txt', dst: '/b.txt' });
  });
});

// ── uploadFile ────────────────────────────────────────────────────────────────

describe('uploadFile', () => {
  it('sends multipart POST to /api/files/upload', async () => {
    global.fetch = mockFetch({ status: 'ok', path: '/file.txt', backend: INSTANCE_ID });
    const file = new File(['content'], 'file.txt', { type: 'text/plain' });
    await uploadFile('/', file, INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/upload');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
  });
});

// ── getDownloadToken ──────────────────────────────────────────────────────────

describe('getDownloadToken', () => {
  it('calls /api/files/download-token with backend param', async () => {
    global.fetch = mockFetch({ token: 'signed.token.here', expires_in: 300 });
    const result = await getDownloadToken(INSTANCE_ID);
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('/api/files/download-token');
    expect(url).toContain(`backend=${INSTANCE_ID}`);
    expect(result.token).toBe('signed.token.here');
    expect(result.expires_in).toBe(300);
  });
});

// ── downloadUrl ───────────────────────────────────────────────────────────────

describe('downloadUrl', () => {
  it('fetches a token and returns a URL with ?token= and ?path=', async () => {
    global.fetch = mockFetch({ token: 'mytoken', expires_in: 300 });
    const url = await downloadUrl('/report.pdf', INSTANCE_ID);
    expect(url).toContain('/api/files/download');
    expect(url).toContain('token=mytoken');
    expect(url).toContain('path=');
  });

  it('does NOT use localStorage', async () => {
    global.fetch = mockFetch({ token: 'tok', expires_in: 300 });
    const getSpy = vi.spyOn(Storage.prototype, 'getItem');
    await downloadUrl('/f.txt', INSTANCE_ID);
    expect(getSpy).not.toHaveBeenCalled();
  });
});
