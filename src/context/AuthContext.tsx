import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, AuthErrorResponse } from '../types/auth';
import { AuthService } from '../services/auth';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: () => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);

  useEffect(() => {
    const initAuth = async () => {
      try {
        setLoading(true);
        const result = await AuthService.checkAuth();

        if ('id' in result) {
          setUser(result as User);
        } else {
          // It's an AuthErrorResponse (401)
          const authError = result as AuthErrorResponse;
          setLoginUrl(authError.login_url);
        }
      } catch (err) {
        console.error('Auth check failed', err);
        setError('Failed to check authentication status');
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, []);

  const login = () => {
    if (loginUrl) {
      window.location.href = loginUrl;
    } else {
      // Fallback if loginUrl wasn't fetched yet or in case of error, though unlikely if properly handled
      // We can construct it manually as described in the docs
      window.location.href = AuthService.getLoginUrl();
    }
  };

  const logout = async () => {
    try {
      await AuthService.logout();
      setUser(null);
      // Redirect to home or refresh, as per instructions
      window.location.href = '/';
    } catch (err) {
      console.error('Logout failed', err);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
