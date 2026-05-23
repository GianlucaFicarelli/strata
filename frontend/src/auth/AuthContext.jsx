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
 *     logout:  async () => void,
 *   }
 *
 * Token refresh design
 * --------------------
 * Access tokens are short-lived (default 15 min). A refresh token (30 days,
 * server-side, rotated on each use) is stored alongside in localStorage.
 *
 * On login and on each successful refresh, a proactive refresh is scheduled
 * via setTimeout to fire ~60 s before the access token expires. This means
 * the user never sees a 401 mid-session — the new token is in place before
 * the old one dies.
 *
 * On mount, the remaining access-token lifetime is read from the JWT's exp
 * claim (decoded client-side — no library needed, JWTs are base64). If less
 * than 60 s remain the refresh fires immediately; this handles the "tab was
 * closed and reopened near expiry" case.
 *
 * If the refresh token itself is expired or revoked the user is logged out
 * cleanly (no redirect loop).
 *
 * Design notes
 * ------------
 * - Both tokens are stored in localStorage under 'strata_token' and
 *   'strata_refresh_token'. For a production deployment HttpOnly cookies are
 *   more secure; switch the storage here without touching any other file.
 * - login() is generic: it calls whatever URL the active auth provider
 *   advertises. No JWT-specific code is hard-coded in the UI layer — the only
 *   JWT-aware piece is the refresh scheduling, which is gated on a refresh
 *   token being present.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

const TOKEN_KEY = 'strata_token';
const REFRESH_TOKEN_KEY = 'strata_refresh_token';
// Fire the refresh this many seconds before the access token actually expires.
const REFRESH_BUFFER_SECONDS = 60;

const AuthContext = createContext(null);

// ── JWT helpers ───────────────────────────────────────────────────────────────

/**
 * Return the number of seconds until the JWT expires, or null if the token
 * cannot be decoded or has no exp claim.
 * JWTs are base64url-encoded — no library required.
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
  // Keep a ref to the latest refresh token so the timer closure is always
  // current even after token rotation, without needing it in deps.
  const refreshTokenRef = useRef(localStorage.getItem(REFRESH_TOKEN_KEY));

  // ── Internal helpers ───────────────────────────────────────────────────────

  const clearTokens = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    refreshTokenRef.current = null;
    setToken(null);
    setUser(null);
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const storeTokens = useCallback((accessToken, refreshToken, expiresIn) => {
    localStorage.setItem(TOKEN_KEY, accessToken);
    if (refreshToken) {
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
      refreshTokenRef.current = refreshToken;
    }
    setToken(accessToken);
    return expiresIn; // seconds; caller schedules the timer
  }, []);

  // scheduleRefresh is defined after performRefresh — forward-ref via useRef.
  const scheduleRefreshRef = useRef(null);

  const performRefresh = useCallback(async () => {
    const rt = refreshTokenRef.current;
    if (!rt) {
      clearTokens();
      return;
    }
    try {
      const res = await fetch('/api/plugins/auth_jwt/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) {
        // Refresh token expired or revoked — log the user out silently.
        clearTokens();
        return;
      }
      const data = await res.json();
      storeTokens(data.access_token, data.refresh_token, data.expires_in);
      // Schedule the next proactive refresh.
      scheduleRefreshRef.current?.(data.expires_in);
    } catch {
      // Network error — don't log out; the user may be briefly offline.
      // The next API call will get a 401 and the user will be asked to log in.
    }
  }, [clearTokens, storeTokens]);

  const scheduleRefresh = useCallback(
    (expiresInSeconds) => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
      if (!refreshTokenRef.current) return; // no refresh token — nothing to schedule

      const delayMs = Math.max(0, (expiresInSeconds - REFRESH_BUFFER_SECONDS) * 1000);
      refreshTimerRef.current = setTimeout(performRefresh, delayMs);
    },
    [performRefresh],
  );

  // Wire the forward ref so performRefresh can call scheduleRefresh.
  useEffect(() => {
    scheduleRefreshRef.current = scheduleRefresh;
  }, [scheduleRefresh]);

  // ── Hydrate user from a stored token on mount ──────────────────────────────

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
        // Schedule a proactive refresh based on remaining JWT lifetime.
        const remaining = jwtSecondsUntilExpiry(storedToken);
        if (remaining !== null && refreshTokenRef.current) {
          scheduleRefresh(remaining);
        }
      })
      .catch(() => {
        // Token is stale — try to refresh immediately if we have a refresh token.
        if (refreshTokenRef.current) {
          performRefresh().then(() => {
            // After refresh, re-fetch the user profile with the new token.
            const newToken = localStorage.getItem(TOKEN_KEY);
            if (newToken) {
              return fetch('/api/auth/me', {
                headers: { Authorization: `Bearer ${newToken}` },
              })
                .then((r) => r.json())
                .then(setUser);
            }
          }).catch(clearTokens);
        } else {
          clearTokens();
        }
      })
      .finally(() => setLoading(false));
  }, []); // run once on mount

  // Clean up the timer when the provider unmounts.
  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, []);

  // ── Login ──────────────────────────────────────────────────────────────────

  const login = useCallback(
    async (loginUrl, username, password) => {
      const body = new URLSearchParams({ username, password });
      const res = await fetch(loginUrl, { method: 'POST', body });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail?.detail ?? 'Login failed');
      }
      const data = await res.json();

      storeTokens(data.access_token, data.refresh_token, data.expires_in);

      // Schedule proactive refresh if the provider returned a refresh token.
      if (data.refresh_token && data.expires_in) {
        scheduleRefresh(data.expires_in);
      }

      const meRes = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      if (!meRes.ok) throw new Error('Could not load user profile');
      setUser(await meRes.json());
    },
    [storeTokens, scheduleRefresh],
  );

  // ── Logout ─────────────────────────────────────────────────────────────────

  const logout = useCallback(async () => {
    const rt = refreshTokenRef.current;
    clearTokens();
    // Best-effort revocation — don't block the UI on network failure.
    if (rt) {
      fetch('/api/plugins/auth_jwt/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      }).catch(() => {});
    }
  }, [clearTokens]);

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
