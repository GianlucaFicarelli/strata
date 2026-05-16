/**
 * LoginGate
 * ---------
 * Wraps the application shell.  Shows a loading spinner while the token is
 * being verified, the LoginForm when no user is authenticated, and renders
 * children once a valid user is present.
 *
 * Auth provider discovery
 * -----------------------
 * On first render (unauthenticated state) we call GET /api/auth/providers to
 * find out what login endpoint to use.  This keeps the frontend generic: it
 * works with auth_jwt today and with an OIDC provider tomorrow without any
 * code change.
 *
 * If no auth providers are registered (e.g. a dev deployment with no auth
 * plugin loaded) we skip the gate entirely and render children directly.
 */

import { Spin } from 'antd';
import { useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import LoginForm from './LoginForm';

export default function LoginGate({ children }) {
  const { user, loading } = useAuth();
  const [providers, setProviders] = useState(null); // null = not yet loaded
  const [providersLoading, setProvidersLoading] = useState(true);

  useEffect(() => {
    fetch('/api/auth/providers')
      .then((r) => r.json())
      .then((p) => setProviders(p))
      .catch(() => setProviders([]))
      .finally(() => setProvidersLoading(false));
  }, []);

  // Still verifying the stored token or loading provider list
  if (loading || providersLoading) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          background: '#141414',
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  // No auth plugins loaded → bypass the gate (dev / local mode)
  if (providers.length === 0) {
    return children;
  }

  // Auth plugins loaded but user not authenticated → show login form
  if (!user) {
    return <LoginForm providers={providers} />;
  }

  // Authenticated → render the app
  return children;
}
