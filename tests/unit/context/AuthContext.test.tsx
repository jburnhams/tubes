import { render, screen, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../../src/context/AuthContext';
import { AuthService } from '../../../src/services/auth';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import React from 'react';

// Mock AuthService
vi.mock('../../../src/services/auth', () => ({
  AuthService: {
    checkAuth: vi.fn(),
    logout: vi.fn(),
    getLoginUrl: vi.fn(),
  },
}));

// Mock window.location
const originalLocation = window.location;

describe('AuthContext Unit Tests', () => {
    let locationHref: string;

    beforeEach(() => {
        vi.resetAllMocks();
        locationHref = '';

        // Mock window.location properties
        delete (window as any).location;
        (window as any).location = {
            ...originalLocation,
            set href(val: string) {
                locationHref = val;
            },
            get href() {
                return locationHref;
            }
        };
    });

    afterEach(() => {
        (window as any).location = originalLocation;
    });

    const TestComponent = () => {
        const { user, login, logout, loading, error } = useAuth();
        return (
            <div>
                <div data-testid="loading">{loading.toString()}</div>
                <div data-testid="error">{error}</div>
                <div data-testid="user">{user ? user.name : 'No User'}</div>
                <button onClick={login}>Login</button>
                <button onClick={logout}>Logout</button>
            </div>
        );
    };

    it('handles successful authentication', async () => {
        const mockUser = { id: 1, name: 'Test User' };
        (AuthService.checkAuth as any).mockResolvedValue(mockUser);

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByTestId('loading')).toHaveTextContent('false');
            expect(screen.getByTestId('user')).toHaveTextContent('Test User');
        });
    });

    it('handles 401 redirect flow', async () => {
        const mockAuthError = { login_url: 'http://login.com' };
        (AuthService.checkAuth as any).mockResolvedValue(mockAuthError);

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => {
            // Verify redirect happened
            expect(locationHref).toBe('http://login.com');
            // In 401 flow, loading stays true to prevent flash
            expect(screen.getByTestId('loading')).toHaveTextContent('true');
        });
    });

    it('handles network error during checkAuth', async () => {
        const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        (AuthService.checkAuth as any).mockRejectedValue(new Error('Network Error'));

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByTestId('loading')).toHaveTextContent('false');
            expect(screen.getByTestId('error')).toHaveTextContent('Failed to check authentication status');
        });
        consoleSpy.mockRestore();
    });

    it('login uses fallback URL if not redirected yet', async () => {
        // Initial state where checkAuth hasn't returned login_url yet or failed silently in a way that allows login
        // We mock it to reject, setting loading to false but not setting loginUrl
        (AuthService.checkAuth as any).mockRejectedValue(new Error('Auth failed'));
        (AuthService.getLoginUrl as any).mockReturnValue('http://fallback-login.com');

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

        const loginButton = screen.getByText('Login');

        act(() => {
            loginButton.click();
        });

        expect(locationHref).toBe('http://fallback-login.com');
    });

    it('login uses stored loginUrl from 401 response', async () => {
         const mockAuthError = { login_url: 'http://stored-login.com' };
         (AuthService.checkAuth as any).mockResolvedValue(mockAuthError);

         render(
             <AuthProvider>
                 <TestComponent />
             </AuthProvider>
         );

         await waitFor(() => {
             expect(locationHref).toBe('http://stored-login.com');
         });

         // Reset href to verify button click sets it again
         locationHref = '';

         const loginButton = screen.getByText('Login');
         act(() => {
             loginButton.click();
         });

         expect(locationHref).toBe('http://stored-login.com');
    });

    it('logout redirects to home on success', async () => {
        const mockUser = { id: 1, name: 'Test User' };
        (AuthService.checkAuth as any).mockResolvedValue(mockUser);
        (AuthService.logout as any).mockResolvedValue(undefined);

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('Test User'));

        const logoutButton = screen.getByText('Logout');
        await act(async () => {
            logoutButton.click();
        });

        expect(locationHref).toBe('/');
        expect(screen.getByTestId('user')).toHaveTextContent('No User');
    });

    it('handles logout failure', async () => {
        const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        const mockUser = { id: 1, name: 'Test User' };
        (AuthService.checkAuth as any).mockResolvedValue(mockUser);
        (AuthService.logout as any).mockRejectedValue(new Error('Logout Failed'));

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('Test User'));

        const logoutButton = screen.getByText('Logout');
        await act(async () => {
            logoutButton.click();
        });

        expect(consoleSpy).toHaveBeenCalledWith('Logout failed', expect.any(Error));
        // User should still be logged in if logout failed? The code doesn't set user to null on error.
        expect(screen.getByTestId('user')).toHaveTextContent('Test User');
        consoleSpy.mockRestore();
    });
});
