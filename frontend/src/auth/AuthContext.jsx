/**
 * AuthContext
 * -----------
 * Provides the application-wide authentication state.
 *
 * Context value shape:
 *   {
 *     user:    { id, username, is_admin } | null,
 *     token:   string | null,
 *     loading: boolean,
 *     login:   async (loginUrl, username, password) => void,
 *     logout:  async () => void,
 *   }
 *
 * Token storage
 * -------------
 * Access token  → localStorage['strata_token'].
 *   Short-lived (default 15 min). Readable by JS so it can be injected into
 *   Authorization headers.  XSS risk is mitigated by its short lifetime.
 *
 * Refresh token → HttpOnly cookie 'strata_refresh_token' (set by the server).
 *   Not readable by JS at all — the browser sends it automatically on requests
 *   to /api/plugins/auth_jwt/*.  This is the primary XSS defence.
 *   SameSite=Strict on the cookie prevents CSRF.
 *
 * Proactive refresh
 * -----------------
 * On login and on each successful refresh a setTimeout is scheduled to fire
 * ~60 s before the access token expires.  The refresh call carries no body —
 * the HttpOnly cookie is sent automatically by the browser.  This means the
 * user never sees a 401 mid-session.
 *
 * On mount the remaining JWT lifetime is read from the token's exp claim
 * (base64-decoded client-side, no library needed) and the refresh is
 * scheduled accordingly.  If the access token is already stale the refresh
 * fires immediately; the HttpOnly cookie handles the authentication.
 *
 * If the refresh token is expired or revoked the user is logged out silently.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

const TOKEN_KEY = 'strata_token';
const REFRESH_BUFFER_SECONDS = 60;

const AuthContext = createContext(null);

// ── JWT helpers ───────────────────────────────────────────────────────────────

/**
 * Return the number of seconds until the JWT expires, or null if the token
 * cannot be decoded or has no exp claim.
 */
function jwtSecondsUntilExpiry(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    if (!payload.exp) return null;
    return payload.exp - Math.floor(Date.now() / 1000);
  } catch {
    return null;
  }
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(true);
  const refreshTimerRef = useRef(null);
  // Track whether we have a refresh cookie available. We can't read the
  // HttpOnly cookie from JS — instead we mirror the flag in a ref that is
  // set true on login/refresh and false on logout/clear.
  const hasRefreshCookieRef = useRef(
    // On mount: assume we have a refresh cookie if we also have an access
    // token in localStorage (they are always written together).
    localStorage.getItem(TOKEN_KEY) !== null,
  );

  // scheduleRefresh is defined after performRefresh — forward-ref via useRef.
  const scheduleRefreshRef = useRef(null);

  // ── Internal helpers ───────────────────────────────────────────────────────

  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    hasRefreshCookieRef.current = false;
    setToken(null);
    setUser(null);
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const applyNewAccessToken = useCallback((accessToken) => {
    localStorage.setItem(TOKEN_KEY, accessToken);
    hasRefreshCookieRef.current = true;
    setToken(accessToken);
  }, []);

  const performRefresh = useCallback(async () => {
    if (!hasRefreshCookieRef.current) {
      clearSession();
      return;
    }
    try {
      // No body needed — the HttpOnly cookie is sent automatically.
      // credentials: 'include' is required for cookies to be sent on
      // cross-origin requests (Vite dev server vs FastAPI on different ports).
      const res = await fetch('/api/plugins/auth_jwt/refresh', {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) {
        // Refresh token expired or revoked — log out silently.
        clearSession();
        return;
      }
      const data = await res.json();
      applyNewAccessToken(data.access_token);
      scheduleRefreshRef.current?.(data.expires_in);
    } catch {
      // Network error — stay logged in; the next API call will surface a 401
      // if the token is truly dead by then.
    }
  }, [clearSession, applyNewAccessToken]);

  const scheduleRefresh = useCallback(
    (expiresInSeconds) => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
      if (!hasRefreshCookieRef.current) return;
      const delayMs = Math.max(0, (expiresInSeconds - REFRESH_BUFFER_SECONDS) * 1000);
      refreshTimerRef.current = setTimeout(performRefresh, delayMs);
    },
    [performRefresh],
  );

  useEffect(() => {
    scheduleRefreshRef.current = scheduleRefresh;
  }, [scheduleRefresh]);

  // ── Hydrate on mount ───────────────────────────────────────────────────────

  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — runs once on mount only
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      setLoading(false);
      return;
    }

    fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${storedToken}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error('Token invalid');
        return res.json();
      })
      .then((u) => {
        setUser(u);
        const remaining = jwtSecondsUntilExpiry(storedToken);
        if (remaining !== null) scheduleRefresh(remaining);
      })
      .catch(() => {
        // Access token stale — attempt silent refresh via the HttpOnly cookie.
        performRefresh()
          .then(() => {
            const newToken = localStorage.getItem(TOKEN_KEY);
            if (newToken) {
              return fetch('/api/auth/me', {
                headers: { Authorization: `Bearer ${newToken}` },
              })
                .then((r) => r.json())
                .then(setUser);
            }
          })
          .catch(clearSession);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, []);

  // ── Login ──────────────────────────────────────────────────────────────────

  const login = useCallback(
    async (loginUrl, username, password) => {
      // credentials: 'include' so the server's Set-Cookie response header is
      // accepted and the HttpOnly cookie is stored by the browser.
      const res = await fetch(loginUrl, {
        method: 'POST',
        body: new URLSearchParams({ username, password }),
        credentials: 'include',
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail?.detail ?? 'Login failed');
      }
      const data = await res.json();

      applyNewAccessToken(data.access_token);
      if (data.expires_in) scheduleRefresh(data.expires_in);

      const meRes = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      if (!meRes.ok) throw new Error('Could not load user profile');
      setUser(await meRes.json());
    },
    [applyNewAccessToken, scheduleRefresh],
  );

  // ── Logout ─────────────────────────────────────────────────────────────────

  const logout = useCallback(async () => {
    clearSession();
    // Best-effort revocation. The server reads the cookie and clears it.
    // No body needed — the cookie is sent automatically via credentials: include.
    fetch('/api/plugins/auth_jwt/logout', {
      method: 'POST',
      credentials: 'include',
    }).catch(() => {});
  }, [clearSession]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
