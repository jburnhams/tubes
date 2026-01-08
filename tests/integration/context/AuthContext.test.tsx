import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { AuthProvider, useAuth } from '@/src/context/AuthContext';
import { AuthService } from '@/src/services/auth';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock AuthService
vi.mock('@/src/services/auth', () => ({
  AuthService: {
    checkAuth: vi.fn(),
    logout: vi.fn(),
    getLoginUrl: vi.fn(),
  },
}));

// Test component to consume context
const TestComponent = () => {
  const { user, loading, error, login, logout } = useAuth();

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      {user ? (
        <>
          <div data-testid="user-name">{user.name}</div>
          <button onClick={logout}>Logout</button>
        </>
      ) : (
        <button onClick={login}>Login</button>
      )}
    </div>
  );
};

describe('AuthContext Integration', () => {
  const mockUser = { id: 1, name: 'Test User' };

  // Save original location to restore it later
  const originalLocation = window.location;

  beforeEach(() => {
    vi.resetAllMocks();

    // In JSDOM, window.location is read-only but configurable in some versions.
    // Ideally, we should not delete it.
    // However, to mock href assignment, we can try to use Object.defineProperty if it allows.
    // If we can't completely replace window.location, we can just spy on assignments if the code was using assign().
    // Since the code uses direct assignment (window.location.href = ...), we need a writable property.
    // The previous solution (Object.defineProperty) might work depending on JSDOM version configured.
    // Let's try to do it safely by deleting it first (if configurable) or just modifying href if possible.

    // A robust way for JSDOM:
    delete (window as any).location;
    (window as any).location = { href: 'http://localhost:3000' };
  });

  afterEach(() => {
    vi.restoreAllMocks();
    (window as any).location = originalLocation;
  });

  it('provides loading state initially', async () => {
    (AuthService.checkAuth as any).mockImplementation(() => new Promise(() => {})); // Never resolves

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('loads user on successful checkAuth', async () => {
    (AuthService.checkAuth as any).mockResolvedValue(mockUser);

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('user-name')).toHaveTextContent('Test User');
    });
    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
  });

  it('handles authentication error (not logged in)', async () => {
    const authError = { login_url: 'http://login.url' };
    (AuthService.checkAuth as any).mockResolvedValue(authError);

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Login')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('user-name')).not.toBeInTheDocument();
  });

  it('handles unexpected error', async () => {
    (AuthService.checkAuth as any).mockRejectedValue(new Error('Network error'));

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error: Failed to check authentication status')).toBeInTheDocument();
    });
  });

  it('redirects to login url on login click', async () => {
    const authError = { login_url: 'http://external-login.com' };
    (AuthService.checkAuth as any).mockResolvedValue(authError);

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Login')).toBeInTheDocument();
    });

    const loginButton = screen.getByText('Login');
    fireEvent.click(loginButton);

    // Check if window.location.href changed
    expect(window.location.href).toBe('http://external-login.com');
  });

  it('calls logout and redirects', async () => {
    (AuthService.checkAuth as any).mockResolvedValue(mockUser);
    (AuthService.logout as any).mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Logout')).toBeInTheDocument();
    });

    const logoutButton = screen.getByText('Logout');
    await act(async () => {
        fireEvent.click(logoutButton);
    });

    expect(AuthService.logout).toHaveBeenCalled();
    expect(window.location.href).toBe('/');
  });
});
