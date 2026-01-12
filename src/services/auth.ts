import { User, AuthErrorResponse } from '../types/auth';
import { ConfigService } from './config';

// Default to empty string to allow Vite proxy to handle requests to vps.jonathanburnhams.com
// Set VITE_API_URL in .env if an absolute URL is required (e.g. production without proxy)
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const getHeaders = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const cookie = ConfigService.getCookie();
  if (cookie) {
    headers['h-Cookie'] = cookie;
  }
  return headers;
};

export class AuthService {
  static async checkAuth(): Promise<User | AuthErrorResponse> {
    const response = await fetch(`${API_BASE_URL}/api/session`, {
      method: 'GET',
      headers: getHeaders(),
      credentials: 'include',
    });

    if (response.ok) {
      const data = await response.json();
      const user = data.user;
      user.session_id = data.id;
      return user;
    } else if (response.status === 401) {
      return response.json();
    } else {
      throw new Error(`Auth check failed with status: ${response.status}`);
    }
  }

  static async logout(): Promise<void> {
    const headers: Record<string, string> = {};
    const cookie = ConfigService.getCookie();
    if (cookie) {
      headers['h-Cookie'] = cookie;
    }
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: 'POST',
      headers,
      credentials: 'include',
    });
  }

  static getLoginUrl(redirectUrl: string = window.location.href): string {
    return `${API_BASE_URL}/auth/login?redirect=${encodeURIComponent(redirectUrl)}`;
  }
}
