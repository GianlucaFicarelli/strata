/**
 * Unit/integration tests for src/auth/AuthContext.jsx
 *
 * Tests cover: initial unauthenticated state, token hydration on mount,
 * login() success and failure paths, logout(), and proactive token refresh.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from '../../auth/AuthContext';

const TOKEN_KEY = 'strata_token';
const REFRESH_TOKEN_KEY = 'strata_refresh_token';

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

/** Build a minimal JWT with a given exp claim (seconds since epoch). */
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

// ── Token hydration on mount ──────────────────────────────────────────────────

describe('token hydration', () => {
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
    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({
        headers: { Authorization: 'Bearer valid.jwt.token' },
      }),
    );
  });

  it('clears token when /api/auth/me returns non-ok and no refresh token', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired.token');
    global.fetch = vi.fn().mockResolvedValue({ ok: false });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('clears token when fetch rejects (network error) and no refresh token', async () => {
    localStorage.setItem(TOKEN_KEY, 'some.token');
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('schedules a proactive refresh based on remaining JWT lifetime', async () => {
    const expiry = Math.floor(Date.now() / 1000) + 900; // 15 min from now
    const jwt = makeJwt(expiry);
    localStorage.setItem(TOKEN_KEY, jwt);
    localStorage.setItem(REFRESH_TOKEN_KEY, 'rt-stored');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ME_RESPONSE,
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Advance to just before the refresh fires (900 - 60 = 840 s).
    // Mock the refresh endpoint for when the timer fires.
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: 'new.access',
          refresh_token: 'new.refresh',
          expires_in: 900,
        }),
      });

    await act(async () => {
      vi.advanceTimersByTime(841_000); // just past the 840 s mark
      await Promise.resolve(); // flush microtasks
    });

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/plugins/auth_jwt/refresh',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(localStorage.getItem(TOKEN_KEY)).toBe('new.access');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('new.refresh');
  });
});

// ── login() ───────────────────────────────────────────────────────────────────

describe('login()', () => {
  it('sets token and user on success, stores refresh token', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: 'new.jwt',
          refresh_token: 'rt-123',
          expires_in: 900,
          token_type: 'bearer',
        }),
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

    expect(result.current.user).toEqual({ id: 'u2', username: 'bob', is_admin: false });
    expect(result.current.token).toBe('new.jwt');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('new.jwt');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('rt-123');
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
  it('clears user, both tokens, and calls revocation endpoint', async () => {
    localStorage.setItem(TOKEN_KEY, 'live.token');
    localStorage.setItem(REFRESH_TOKEN_KEY, 'live.refresh');

    global.fetch = vi
      .fn()
      // mount hydration
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 'u3', username: 'carol', is_admin: false }),
      })
      // logout revocation
      .mockResolvedValueOnce({ ok: true });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).not.toBeNull();

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/plugins/auth_jwt/logout',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ refresh_token: 'live.refresh' }),
      }),
    );
  });
});

// ── Proactive refresh ─────────────────────────────────────────────────────────

describe('performRefresh()', () => {
  it('logs out silently when refresh token is rejected by the server', async () => {
    const expiry = Math.floor(Date.now() / 1000) + 900;
    localStorage.setItem(TOKEN_KEY, makeJwt(expiry));
    localStorage.setItem(REFRESH_TOKEN_KEY, 'expired-rt');

    global.fetch = vi
      .fn()
      // hydration
      .mockResolvedValueOnce({ ok: true, json: async () => ME_RESPONSE })
      // refresh call — server rejects (refresh token expired)
      .mockResolvedValueOnce({ ok: false });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      vi.advanceTimersByTime(841_000);
      await Promise.resolve();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });
});

// ── useAuth() outside provider ────────────────────────────────────────────────

describe('useAuth() guard', () => {
  it('throws when used outside AuthProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow('useAuth must be used inside <AuthProvider>');
    spy.mockRestore();
  });
});
