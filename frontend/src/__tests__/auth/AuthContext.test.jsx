/**
 * Unit/integration tests for src/auth/AuthContext.jsx
 *
 * The refresh token lives in an HttpOnly cookie — JS cannot read it.
 * Tests verify that:
 * - login() stores only the access token in localStorage (not the refresh token)
 * - refresh calls carry credentials: 'include' (no body token needed)
 * - logout() calls the revocation endpoint with credentials: 'include' (no body)
 * - proactive refresh is scheduled and fires at the right time
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from '../../auth/AuthContext';

const TOKEN_KEY = 'strata_token';

function wrapper({ children }) {
  return <AuthProvider>{children}</AuthProvider>;
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeJwt(expSeconds) {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({ sub: 'u1', exp: expSeconds }));
  return `${header}.${payload}.sig`;
}

const ME_RESPONSE = { id: 'u1', username: 'alice', is_admin: false };

// ── Initial state ─────────────────────────────────────────────────────────────

describe('initial state — no stored token', () => {
  it('user is null after mount', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });
});

// ── Token hydration ───────────────────────────────────────────────────────────

describe('token hydration on mount', () => {
  it('fetches /api/auth/me with stored token and sets user', async () => {
    localStorage.setItem(TOKEN_KEY, 'valid.jwt.token');
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ME_RESPONSE,
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toEqual(ME_RESPONSE);
    expect(result.current.token).toBe('valid.jwt.token');
  });

  it('attempts silent refresh when /api/auth/me returns non-ok', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired.token');
    global.fetch = vi
      .fn()
      // /api/auth/me fails
      .mockResolvedValueOnce({ ok: false })
      // /api/plugins/auth_jwt/refresh succeeds (cookie sent automatically)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'fresh.token', expires_in: 900 }),
      })
      // /api/auth/me with new token
      .mockResolvedValueOnce({ ok: true, json: async () => ME_RESPONSE });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toEqual(ME_RESPONSE);
    expect(localStorage.getItem(TOKEN_KEY)).toBe('fresh.token');

    // Verify refresh was called with credentials: include and no body.
    const refreshCall = global.fetch.mock.calls.find(([url]) => url.includes('/refresh'));
    expect(refreshCall).toBeDefined();
    const [, opts] = refreshCall;
    expect(opts.credentials).toBe('include');
    expect(opts.body).toBeUndefined();
  });

  it('clears session when /api/auth/me fails and refresh also fails', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired.token');
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false }) // /api/auth/me
      .mockResolvedValueOnce({ ok: false }); // /refresh

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('schedules proactive refresh based on remaining JWT lifetime', async () => {
    const expiry = Math.floor(Date.now() / 1000) + 900; // 15 min from now
    const jwt = makeJwt(expiry);
    localStorage.setItem(TOKEN_KEY, jwt);

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ME_RESPONSE,
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Set up the refresh mock for when the timer fires (at 900 - 60 = 840 s).
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: 'rotated.token', expires_in: 900 }),
    });

    await act(async () => {
      vi.advanceTimersByTime(841_000);
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/plugins/auth_jwt/refresh',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
    expect(localStorage.getItem(TOKEN_KEY)).toBe('rotated.token');
  });
});

// ── login() ───────────────────────────────────────────────────────────────────

describe('login()', () => {
  it('stores only the access token in localStorage (no refresh token)', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        // Server no longer sends refresh_token in the body — it's in the cookie.
        json: async () => ({ access_token: 'new.jwt', token_type: 'bearer', expires_in: 900 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 'u2', username: 'bob', is_admin: false }),
      });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login('/api/plugins/auth_jwt/login', 'bob', 'password123');
    });

    expect(result.current.token).toBe('new.jwt');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('new.jwt');
    // No refresh token in localStorage — it lives in the HttpOnly cookie.
    expect(localStorage.getItem('strata_refresh_token')).toBeNull();
  });

  it('sends login request with credentials: include', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'tok', expires_in: 900 }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ME_RESPONSE });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login('/api/plugins/auth_jwt/login', 'alice', 'pw');
    });

    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.credentials).toBe('include');
  });

  it('throws and leaves user null on bad credentials', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Incorrect username or password' }),
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.login('/api/plugins/auth_jwt/login', 'bad', 'bad');
      }),
    ).rejects.toThrow('Incorrect username or password');

    expect(result.current.user).toBeNull();
  });
});

// ── logout() ─────────────────────────────────────────────────────────────────

describe('logout()', () => {
  it('clears user and access token, calls revocation with credentials: include and no body', async () => {
    localStorage.setItem(TOKEN_KEY, 'live.token');

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ME_RESPONSE }) // hydration
      .mockResolvedValueOnce({ ok: true }); // logout

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).not.toBeNull();

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();

    // Allow the fire-and-forget fetch to resolve.
    await act(async () => {
      await Promise.resolve();
    });

    const logoutCall = global.fetch.mock.calls.find(([url]) => url.includes('/logout'));
    expect(logoutCall).toBeDefined();
    const [, opts] = logoutCall;
    expect(opts.method).toBe('POST');
    expect(opts.credentials).toBe('include');
    // No body — the cookie is sent automatically.
    expect(opts.body).toBeUndefined();
  });
});

// ── Proactive refresh ─────────────────────────────────────────────────────────

describe('performRefresh()', () => {
  it('logs out silently when refresh returns non-ok', async () => {
    const expiry = Math.floor(Date.now() / 1000) + 900;
    localStorage.setItem(TOKEN_KEY, makeJwt(expiry));

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ME_RESPONSE }) // hydration
      .mockResolvedValueOnce({ ok: false }); // refresh rejected

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      vi.advanceTimersByTime(841_000);
      await Promise.resolve();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

// ── useAuth() guard ───────────────────────────────────────────────────────────

describe('useAuth() guard', () => {
  it('throws when used outside AuthProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow('useAuth must be used inside <AuthProvider>');
    spy.mockRestore();
  });
});
