/**
 * AuthContext
 * -----------
 * Provides the application-wide authentication state.
 *
 * Context value shape:
 *   {
 *     user:    { id, username, is_admin } | null,
 *     token:   string | null,
 *     loading: boolean,   // true while hydrating from localStorage on mount
 *     login:   async (loginUrl, username, password) => void,
 *     logout:  () => void,
 *   }
 *
 * Design notes
 * ------------
 * - Token is stored in localStorage under 'strata_token'.  For a production
 *   deployment an HttpOnly cookie is more secure; switch the storage here
 *   without touching any other file.
 * - login() is generic: it calls whatever URL the active auth provider
 *   advertises via GET /api/auth/providers → login_url.  The LoginForm
 *   passes that URL in.  No JWT-specific code lives here.
 * - On mount we attempt to re-hydrate the user by calling GET /api/auth/me
 *   with the stored token.  If the token is expired or missing, the user
 *   stays null and the LoginGate will redirect.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

const TOKEN_KEY = 'strata_token';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [token, setToken]     = useState(() => localStorage.getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(true);

  // ── Hydrate user from a stored token ──────────────────────────────────────

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => {
        if (!res.ok) throw new Error('Token invalid');
        return res.json();
      })
      .then(u => setUser(u))
      .catch(() => {
        // Token is stale — clear it so the user sees the login form.
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []); // run once on mount

  // ── Login ─────────────────────────────────────────────────────────────────

  const login = useCallback(async (loginUrl, username, password) => {
    // OAuth2 password flow — application/x-www-form-urlencoded
    const body = new URLSearchParams({ username, password });
    const res = await fetch(loginUrl, { method: 'POST', body });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? 'Login failed');
    }
    const data = await res.json();
    const newToken = data.access_token;

    localStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);

    // Fetch the user profile with the new token.
    const meRes = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${newToken}` },
    });
    if (!meRes.ok) throw new Error('Could not load user profile');
    setUser(await meRes.json());
  }, []);

  // ── Logout ────────────────────────────────────────────────────────────────

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Hook: access the auth context from any component. */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
