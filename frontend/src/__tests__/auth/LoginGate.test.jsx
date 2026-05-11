/**
 * Tests for LoginGate and LoginForm.
 *
 * LoginGate renders children when authenticated, the login form when not,
 * and passes through (no gate) when no providers are registered.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock AuthContext so we can control auth state precisely
vi.mock('../../auth/AuthContext', () => {
  const actual = vi.importActual('../../auth/AuthContext');
  return {
    ...actual,
    useAuth: vi.fn(),
    AuthProvider: ({ children }) => children,
  };
});

import { useAuth } from '../../auth/AuthContext';
import LoginGate from '../../auth/LoginGate';
import LoginForm from '../../auth/LoginForm';

// ── LoginGate ─────────────────────────────────────────────────────────────────

describe('LoginGate', () => {
  const CHILD_TEXT = 'App content';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a spinner while loading', async () => {
    useAuth.mockReturnValue({ user: null, loading: true });
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });

    render(<LoginGate><div>{CHILD_TEXT}</div></LoginGate>);
    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
  });

  it('renders children directly when no providers are registered', async () => {
    useAuth.mockReturnValue({ user: null, loading: false });
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });

    render(<LoginGate><div>{CHILD_TEXT}</div></LoginGate>);
    await waitFor(() => expect(screen.getByText(CHILD_TEXT)).toBeInTheDocument());
  });

  it('shows LoginForm when providers exist but user is not authenticated', async () => {
    useAuth.mockReturnValue({ user: null, loading: false });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: 'password', name: 'Password', login_url: '/api/plugins/jwt_auth/login' }],
    });

    render(<LoginGate><div>{CHILD_TEXT}</div></LoginGate>);
    await waitFor(() => expect(screen.getByPlaceholderText('Username')).toBeInTheDocument());
    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
  });

  it('renders children when user is authenticated', async () => {
    useAuth.mockReturnValue({
      user: { id: 'u1', username: 'alice', is_admin: false },
      loading: false,
    });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: 'password', name: 'Password', login_url: '/api/plugins/jwt_auth/login' }],
    });

    render(<LoginGate><div>{CHILD_TEXT}</div></LoginGate>);
    await waitFor(() => expect(screen.getByText(CHILD_TEXT)).toBeInTheDocument());
  });
});

// ── LoginForm ─────────────────────────────────────────────────────────────────

const PROVIDERS = [
  { id: 'password', name: 'Password Auth', login_url: '/api/plugins/jwt_auth/login' },
];

describe('LoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders username and password fields', () => {
    useAuth.mockReturnValue({ login: vi.fn() });
    render(<LoginForm providers={PROVIDERS} />);
    expect(screen.getByPlaceholderText('Username')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Password')).toBeInTheDocument();
  });

  it('renders Sign in button', () => {
    useAuth.mockReturnValue({ login: vi.fn() });
    render(<LoginForm providers={PROVIDERS} />);
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('does not show provider picker with only one provider', () => {
    useAuth.mockReturnValue({ login: vi.fn() });
    render(<LoginForm providers={PROVIDERS} />);
    // The "Sign in with" select should not appear
    expect(screen.queryByText('Sign in with')).not.toBeInTheDocument();
  });

  it('shows provider picker with multiple providers', () => {
    useAuth.mockReturnValue({ login: vi.fn() });
    const providers = [
      ...PROVIDERS,
      { id: 'sso', name: 'SSO', login_url: '/api/plugins/sso/login' },
    ];
    render(<LoginForm providers={providers} />);
    expect(screen.getByText('Password Auth')).toBeInTheDocument();
  });

  it('calls login() with correct args on submit', async () => {
    const mockLogin = vi.fn().mockResolvedValue(undefined);
    useAuth.mockReturnValue({ login: mockLogin });

    render(<LoginForm providers={PROVIDERS} />);

    await userEvent.type(screen.getByPlaceholderText('Username'), 'alice');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'secret123');
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith(
        '/api/plugins/jwt_auth/login',
        'alice',
        'secret123',
      );
    });
  });

  it('displays error message when login() throws', async () => {
    const mockLogin = vi.fn().mockRejectedValue(new Error('Incorrect username or password'));
    useAuth.mockReturnValue({ login: mockLogin });

    render(<LoginForm providers={PROVIDERS} />);

    await userEvent.type(screen.getByPlaceholderText('Username'), 'bad');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'bad');
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Incorrect username or password')).toBeInTheDocument();
    });
  });
});
