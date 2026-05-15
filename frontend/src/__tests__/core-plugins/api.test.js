/**
 * Unit tests for src/core-plugins/api.js
 *
 * All tests mock global.fetch — no real network calls.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  listBackends,
  listDir,
  deleteEntry,
  makeDir,
  moveEntry,
  downloadUrl,
  uploadFile,
} from '../../core-plugins/api';

function mockFetch(json, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => json,
    text: async () => JSON.stringify(json),
  });
}

describe('listBackends', () => {
  it('calls /api/backends and returns json', async () => {
    const backends = [{ id: 'storage_local', name: 'Local' }];
    global.fetch = mockFetch(backends);

    const result = await listBackends();
    expect(result).toEqual(backends);
    // api.js always passes a headers object (empty when no token is stored)
    expect(global.fetch).toHaveBeenCalledWith('/api/backends', expect.objectContaining({ headers: expect.any(Object) }));
  });

  it('throws on non-ok response', async () => {
    global.fetch = mockFetch({ detail: 'error' }, false, 500);
    await expect(listBackends()).rejects.toThrow();
  });
});

describe('listDir', () => {
  it('calls /api/files/list with correct query params', async () => {
    global.fetch = mockFetch([]);
    await listDir('/photos', 'storage_local');
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('/api/files/list');
    expect(url).toContain('path=%2Fphotos');
    expect(url).toContain('backend=storage_local');
  });

  it('uses "/" and "storage_local" as defaults', async () => {
    global.fetch = mockFetch([]);
    await listDir();
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('path=%2F');
    expect(url).toContain('backend=storage_local');
  });
});

describe('deleteEntry', () => {
  it('sends DELETE request with correct params', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await deleteEntry('/old.txt', 'storage_local');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/delete');
    expect(opts.method).toBe('DELETE');
  });
});

describe('makeDir', () => {
  it('sends POST to mkdir with path and backend', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await makeDir('/new-folder', 'storage_local');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/mkdir');
    expect(opts.method).toBe('POST');
    expect(url).toContain('new-folder');
  });
});

describe('moveEntry', () => {
  it('sends POST with JSON body', async () => {
    global.fetch = mockFetch({ status: 'ok' });
    await moveEntry('/a.txt', '/b.txt', 'storage_local');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/move');
    expect(opts.method).toBe('POST');
    const body = JSON.parse(opts.body);
    expect(body).toEqual({ src: '/a.txt', dst: '/b.txt', backend: 'storage_local' });
  });
});

describe('downloadUrl', () => {
  beforeEach(() => {
    // Reset fetch so calls from previous describe blocks don't leak in.
    // downloadUrl() is a pure URL builder — it must never call fetch at all.
    global.fetch = vi.fn();
  });

  it('returns a URL without fetching', () => {
    const url = downloadUrl('/file.pdf', 'storage_local');
    expect(url).toContain('/api/files/download');
    expect(url).toContain('file.pdf');
    expect(url).toContain('backend=storage_local');
    expect(global.fetch).not.toHaveBeenCalled?.();
  });
});

describe('uploadFile', () => {
  it('sends POST with FormData', async () => {
    global.fetch = mockFetch({ status: 'ok', path: '/photo.jpg' });
    const fakeFile = new Blob(['data'], { type: 'image/jpeg' });
    fakeFile.name = 'photo.jpg';
    await uploadFile('/uploads', fakeFile, 'storage_local');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/files/upload');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
  });
});
