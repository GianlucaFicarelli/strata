/**
 * Unit/integration tests for src/auth/AuthContext.jsx
 *
 * Tests cover: initial unauthenticated state, token hydration on mount,
 * login() success and failure paths, and logout().
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../auth/AuthContext';

const TOKEN_KEY = 'strata_token';

function wrapper({ children }) {
  return <AuthProvider>{children}</AuthProvider>;
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

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
      json: async () => ({ id: 'u1', username: 'alice', is_admin: false }),
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toEqual({ id: 'u1', username: 'alice', is_admin: false });
    expect(result.current.token).toBe('valid.jwt.token');
    expect(fetch).toHaveBeenCalledWith('/api/auth/me', expect.objectContaining({
      headers: { Authorization: 'Bearer valid.jwt.token' },
    }));
  });

  it('clears token when /api/auth/me returns non-ok', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired.token');

    global.fetch = vi.fn().mockResolvedValue({ ok: false });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('clears token when fetch rejects (network error)', async () => {
    localStorage.setItem(TOKEN_KEY, 'some.token');
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

// ── login() ───────────────────────────────────────────────────────────────────

describe('login()', () => {
  it('sets token and user on success', async () => {
    // Initial mount: no token
    global.fetch = vi.fn()
      // First call: POST /api/plugins/jwt_auth/login
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'new.jwt', token_type: 'bearer' }),
      })
      // Second call: GET /api/auth/me
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 'u2', username: 'bob', is_admin: false }),
      });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login(
        '/api/plugins/jwt_auth/login',
        'bob',
        'password123',
      );
    });

    expect(result.current.user).toEqual({ id: 'u2', username: 'bob', is_admin: false });
    expect(result.current.token).toBe('new.jwt');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('new.jwt');
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
        await result.current.login('/api/plugins/jwt_auth/login', 'bad', 'bad');
      })
    ).rejects.toThrow('Incorrect username or password');

    expect(result.current.user).toBeNull();
  });
});

// ── logout() ─────────────────────────────────────────────────────────────────

describe('logout()', () => {
  it('clears user, token, and localStorage', async () => {
    localStorage.setItem(TOKEN_KEY, 'live.token');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'u3', username: 'carol', is_admin: false }),
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).not.toBeNull();

    act(() => result.current.logout());

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

// ── useAuth() outside provider ────────────────────────────────────────────────

describe('useAuth() guard', () => {
  it('throws when used outside AuthProvider', () => {
    // Suppress the React error boundary console output
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used inside <AuthProvider>'
    );
    spy.mockRestore();
  });
});
