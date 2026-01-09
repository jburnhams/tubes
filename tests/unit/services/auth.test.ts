import { AuthService } from '@/src/services/auth';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('AuthService', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    global.fetch = mockFetch;
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('checkAuth', () => {
    it('returns user data on successful auth', async () => {
      const mockSessionId = 'session-123';
      const mockUser = { id: 1, name: 'Test User' };
      const mockResponse = { id: mockSessionId, user: mockUser };

      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await AuthService.checkAuth();
      expect(result).toEqual({ ...mockUser, session_id: mockSessionId });
      expect(mockFetch).toHaveBeenCalledWith(
        'https://storage.jonathanburnhams.com/api/session',
        expect.objectContaining({
          method: 'GET',
          credentials: 'include',
        })
      );
    });

    it('returns error response on 401', async () => {
      const mockError = { login_url: 'http://example.com/login' };
      mockFetch.mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve(mockError),
      });

      const result = await AuthService.checkAuth();
      expect(result).toEqual(mockError);
    });

    it('throws error on other failures', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });

      await expect(AuthService.checkAuth()).rejects.toThrow('Auth check failed with status: 500');
    });
  });

  describe('logout', () => {
    it('calls logout endpoint', async () => {
      mockFetch.mockResolvedValue({ ok: true });

      await AuthService.logout();
      expect(mockFetch).toHaveBeenCalledWith(
        'https://storage.jonathanburnhams.com/auth/logout',
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
        })
      );
    });
  });

  describe('getLoginUrl', () => {
    it('returns correct login URL with redirect', () => {
      const redirect = 'http://localhost:3000/dashboard';
      const url = AuthService.getLoginUrl(redirect);
      expect(url).toBe(
        'https://storage.jonathanburnhams.com/auth/login?redirect=http%3A%2F%2Flocalhost%3A3000%2Fdashboard'
      );
    });

    it('uses current window location as default', () => {
      // Mock window.location.href if running in node environment where it might not be set as expected
      // But since we are using jsdom, it should be available.
      // However, jsdom default url is 'http://localhost:3000/' usually.

      const url = AuthService.getLoginUrl();
      expect(url).toContain('https://storage.jonathanburnhams.com/auth/login?redirect=');
    });
  });
});
