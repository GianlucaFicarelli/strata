/**
 * Unit tests for src/core-plugins/api.js
 *
 * All tests mock global.fetch — no real network calls.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  deleteEntry,
  downloadUrl,
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

describe('listBackends', () => {
  it('calls /api/storage/backends and returns json', async () => {
    const backends = [{ id: 'abc-123-uuid', name: 'My Local', plugin_id: 'storage_local' }];
    global.fetch = mockFetch(backends);

    const result = await listBackends();
    expect(result).toEqual(backends);
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/storage/backends',
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it('throws on non-ok response', async () => {
    global.fetch = mockFetch({ detail: 'error' }, false, 500);
    await expect(listBackends()).rejects.toThrow();
  });
});

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
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('path=%2F');
    expect(url).toContain(`backend=${INSTANCE_ID}`);
  });
});

describe('deleteEntry', () => {
  it('sends DELETE request with correct params', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await deleteEntry('/old.txt', INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/delete');
    expect(url).toContain(`backend=${INSTANCE_ID}`);
    expect(opts.method).toBe('DELETE');
  });
});

describe('makeDir', () => {
  it('sends POST to mkdir with path and backend', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await makeDir('/new-folder', INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/mkdir');
    expect(opts.method).toBe('POST');
    expect(url).toContain('new-folder');
    expect(url).toContain(`backend=${INSTANCE_ID}`);
  });
});

describe('moveEntry', () => {
  it('sends POST with JSON body including instance UUID as backend', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await moveEntry('/a.txt', '/b.txt', INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/move');
    expect(opts.method).toBe('POST');
    const body = JSON.parse(opts.body);
    expect(body).toEqual({ src: '/a.txt', dst: '/b.txt', backend: INSTANCE_ID });
  });
});

describe('downloadUrl', () => {
  beforeEach(() => {
    // Reset fetch so calls from previous describe blocks don't leak in.
    // downloadUrl() is a pure URL builder — it must never call fetch at all.
    global.fetch = vi.fn();
  });

  it('returns a URL containing the instance UUID without fetching', () => {
    const url = downloadUrl('/file.pdf', INSTANCE_ID);
    expect(url).toContain('/api/files/download');
    expect(url).toContain('file.pdf');
    expect(url).toContain(`backend=${INSTANCE_ID}`);
    expect(global.fetch).not.toHaveBeenCalled?.();
  });
});

describe('uploadFile', () => {
  it('sends POST with FormData and instance UUID as backend', async () => {
    global.fetch = mockFetch({ status: 'ok', path: '/photo.jpg' });
    const fakeFile = new Blob(['data'], { type: 'image/jpeg' });
    fakeFile.name = 'photo.jpg';
    await uploadFile('/uploads', fakeFile, INSTANCE_ID);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/upload');
    expect(url).toContain(`backend=${INSTANCE_ID}`);
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
  });
});

// ── Admin storage API ─────────────────────────────────────────────────────────

import {
  createAdminInstance,
  deleteAdminInstance,
  getUserInstanceConfig,
  listAdminInstances,
  listStorageTemplates,
  listUserInstances,
  updateAdminInstance,
  updateUserInstanceConfig,
} from '../../core-plugins/api';

describe('listStorageTemplates', () => {
  it('calls GET /api/admin/storage/templates with auth header', async () => {
    const templates = [{ plugin_id: 'storage_local', display_name: 'Local' }];
    global.fetch = mockFetch(templates);
    const result = await listStorageTemplates();
    expect(result).toEqual(templates);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/admin/storage/templates');
    expect(opts.headers).toBeDefined();
  });

  it('throws on error', async () => {
    global.fetch = mockFetch({}, false, 403);
    await expect(listStorageTemplates()).rejects.toThrow();
  });
});

describe('listAdminInstances', () => {
  it('calls GET /api/admin/storage/instances', async () => {
    global.fetch = mockFetch([]);
    await listAdminInstances();
    expect(global.fetch.mock.calls[0][0]).toBe('/api/admin/storage/instances');
  });
});

describe('createAdminInstance', () => {
  it('POSTs to /api/admin/storage/instances with JSON body', async () => {
    const payload = { plugin_id: 'storage_local', instance_name: 'A', config: { root: '/x' } };
    global.fetch = mockFetch({ id: 'inst-1', ...payload });
    await createAdminInstance(payload);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/admin/storage/instances');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual(payload);
  });
});

describe('updateAdminInstance', () => {
  it('PUTs to /api/admin/storage/instances/:id', async () => {
    global.fetch = mockFetch({ id: 'inst-1', instance_name: 'B' });
    await updateAdminInstance('inst-1', { instance_name: 'B' });
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/admin/storage/instances/inst-1');
    expect(opts.method).toBe('PUT');
  });
});

describe('deleteAdminInstance', () => {
  it('sends DELETE to /api/admin/storage/instances/:id', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    await deleteAdminInstance('inst-1');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/admin/storage/instances/inst-1');
    expect(opts.method).toBe('DELETE');
  });
});

// ── User storage API ──────────────────────────────────────────────────────────

describe('listUserInstances', () => {
  it('calls GET /api/storage/instances', async () => {
    global.fetch = mockFetch([]);
    await listUserInstances();
    expect(global.fetch.mock.calls[0][0]).toBe('/api/storage/instances');
  });
});

describe('getUserInstanceConfig', () => {
  it('calls GET /api/storage/instances/:id/me', async () => {
    global.fetch = mockFetch({ instance_id: 'inst-1', is_enabled: false });
    await getUserInstanceConfig('inst-1');
    expect(global.fetch.mock.calls[0][0]).toBe('/api/storage/instances/inst-1/me');
  });
});

describe('updateUserInstanceConfig', () => {
  it('PATCHes /api/storage/instances/:id/me with JSON body', async () => {
    global.fetch = mockFetch({ instance_id: 'inst-1', is_enabled: true });
    await updateUserInstanceConfig('inst-1', { is_enabled: true, config: { username: 'alice' } });
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/storage/instances/inst-1/me');
    expect(opts.method).toBe('PATCH');
    const body = JSON.parse(opts.body);
    expect(body.is_enabled).toBe(true);
    expect(body.config.username).toBe('alice');
  });
});
