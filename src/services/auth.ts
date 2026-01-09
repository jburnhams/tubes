import { User, AuthErrorResponse } from '../types/auth';

const API_BASE_URL = 'https://storage.jonathanburnhams.com';

export class AuthService {
  static async checkAuth(): Promise<User | AuthErrorResponse> {
    const response = await fetch(`${API_BASE_URL}/api/session`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
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
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
  }

  static getLoginUrl(redirectUrl: string = window.location.href): string {
    return `${API_BASE_URL}/auth/login?redirect=${encodeURIComponent(redirectUrl)}`;
  }
}
