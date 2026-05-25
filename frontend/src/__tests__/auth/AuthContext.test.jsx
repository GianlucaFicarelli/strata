/**
 * Unit/integration tests for src/auth/AuthContext.jsx
 *
 * The session lives entirely in an HttpOnly cookie — JS cannot read or write it.
 * Tests verify that:
 * - On mount, GET /api/auth/me is called with credentials: include
 * - If /api/auth/me returns 200, user state is populated
 * - If /api/auth/me returns 401, user remains null (cookie absent/expired)
 * - login() POSTs JSON to the provider's login_url and sets user from response
 * - login() sends credentials: include (cookie is set by server Set-Cookie)
 * - logout() clears user state and calls the revocation endpoint
 * - No localStorage or sessionStorage is used
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from '../../auth/AuthContext';

function wrapper({ children }) {
  return <AuthProvider>{children}</AuthProvider>;
}

const ME_RESPONSE = {
  id: 'u1',
  username: 'alice',
  display_name: 'Alice',
  email: null,
  is_admin: false,
};

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

// ── Initial state ─────────────────────────────────────────────────────────────

describe('initial state', () => {
  it('user is null and loading is true before mount completes', () => {
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.user).toBeNull();
    expect(result.current.loading).toBe(true);
  });

  it('user is null after mount when no session cookie is active', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it('calls GET /api/auth/me with credentials: include on mount', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });
    renderHook(() => useAuth(), { wrapper });
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/auth/me',
        expect.objectContaining({ credentials: 'include' }),
      );
    });
  });
});

// ── Session hydration ─────────────────────────────────────────────────────────

describe('session hydration on mount', () => {
  it('sets user when /api/auth/me returns 200', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ME_RESPONSE,
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toEqual(ME_RESPONSE);
  });

  it('leaves user null when /api/auth/me returns 401', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it('does not touch localStorage at any point', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ME_RESPONSE,
    });
    const setSpy = vi.spyOn(Storage.prototype, 'setItem');
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(setSpy).not.toHaveBeenCalled();
  });
});

// ── login() ───────────────────────────────────────────────────────────────────

describe('login()', () => {
  it('POSTs JSON credentials with credentials: include', async () => {
    // Mount with no session
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Login call
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ME_RESPONSE,
    });

    await act(async () => {
      await result.current.login('/api/plugins/auth_local/login', 'alice', 'pw');
    });

    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/plugins/auth_local/login');
    expect(opts.method).toBe('POST');
    expect(opts.credentials).toBe('include');
    expect(opts.headers['Content-Type']).toBe('application/json');
    const body = JSON.parse(opts.body);
    expect(body.username).toBe('alice');
    expect(body.password).toBe('pw');
  });

  it('sets user from login response body', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false }); // mount
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ME_RESPONSE,
    });

    await act(async () => {
      await result.current.login('/api/plugins/auth_local/login', 'alice', 'pw');
    });

    expect(result.current.user).toEqual(ME_RESPONSE);
  });

  it('throws on bad credentials and leaves user null', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false }); // mount
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Invalid username or password' }),
    });

    await expect(
      act(async () => {
        await result.current.login('/api/plugins/auth_local/login', 'x', 'bad');
      }),
    ).rejects.toThrow('Invalid username or password');

    expect(result.current.user).toBeNull();
  });

  it('stores nothing in localStorage on login', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false }); // mount
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ME_RESPONSE,
    });

    const setSpy = vi.spyOn(Storage.prototype, 'setItem');
    await act(async () => {
      await result.current.login('/api/plugins/auth_local/login', 'alice', 'pw');
    });
    expect(setSpy).not.toHaveBeenCalled();
  });
});

// ── logout() ─────────────────────────────────────────────────────────────────

describe('logout()', () => {
  it('clears user and calls revocation endpoint with credentials: include', async () => {
    // Mount with active session
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ME_RESPONSE,
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).not.toBeNull();

    // Logout
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: true });
    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();

    const logoutCall = global.fetch.mock.calls.find(([url]) => url.includes('/logout'));
    expect(logoutCall).toBeDefined();
    const [, opts] = logoutCall;
    expect(opts.method).toBe('POST');
    expect(opts.credentials).toBe('include');
  });

  it('clears user even if revocation request fails', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ME_RESPONSE,
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    global.fetch = vi.fn().mockRejectedValueOnce(new Error('network'));
    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
  });
});

// ── useAuth() guard ───────────────────────────────────────────────────────────

describe('useAuth() guard', () => {
  it('throws when used outside AuthProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used inside <AuthProvider>',
    );
    spy.mockRestore();
  });
});
