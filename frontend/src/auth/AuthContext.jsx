/**
 * AuthContext
 * -----------
 * Provides the application-wide authentication state.
 *
 * Context value shape:
 *   {
 *     user:    { id, username, display_name, email, is_admin } | null,
 *     loading: boolean,
 *     login:   async (loginUrl, username, password) => void,
 *     logout:  async () => void,
 *   }
 *
 * Session model
 * -------------
 * Authentication is entirely cookie-based.  The server sets an HttpOnly
 * `strata_session` cookie on login; the browser sends it automatically on
 * every subsequent request.  No token is stored in JS memory or localStorage.
 *
 * On mount, GET /api/auth/me is called (the cookie is sent automatically).
 * If it returns 200 the user is already logged in.  If it returns 401 the
 * user is shown the login form.
 *
 * There is no proactive token refresh — the server renews the session TTL on
 * every authenticated request (sliding window).  The user is logged out only
 * when the session expires due to inactivity, or when they explicitly log out.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // ── Hydrate on mount ───────────────────────────────────────────────────────
  // The session cookie is sent automatically — no Authorization header needed.

  // biome-ignore lint/correctness/useExhaustiveDependencies: runs once on mount
  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // ── Login ──────────────────────────────────────────────────────────────────

  const login = useCallback(async (loginUrl, username, password) => {
    // credentials: 'include' so the browser stores the Set-Cookie response
    // (required when Vite dev server and FastAPI run on different ports).
    const res = await fetch(loginUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      credentials: 'include',
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? 'Login failed');
    }
    const data = await res.json();
    // The response body carries the user profile directly from the login endpoint.
    setUser(data);
  }, []);

  // ── Logout ─────────────────────────────────────────────────────────────────

  const logout = useCallback(async () => {
    // Optimistically clear local state so the UI transitions immediately.
    setUser(null);
    // Best-effort server-side revocation — clears the Redis session and
    // expires the cookie.  credentials: 'include' sends the session cookie.
    await fetch('/api/plugins/auth_local/logout', {
      method: 'POST',
      credentials: 'include',
    }).catch(() => {});
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
