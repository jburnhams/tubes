// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react';
import { Toolbar } from '@/src/components/Toolbar';
import { vi, Mock } from 'vitest';
import * as AuthContext from '@/src/context/AuthContext';

// Mock the AuthContext
vi.mock('@/src/context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

describe('Toolbar Component', () => {
  const mockUseAuth = AuthContext.useAuth as Mock;

  const mockLogin = vi.fn();
  const mockLogout = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login button when user is not authenticated', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
      login: mockLogin,
      logout: mockLogout,
    });

    render(<Toolbar />);

    // expect(screen.getByText('Tubes')).toBeInTheDocument(); // Logo is an image now
    expect(screen.getByAltText('YouTube Logo')).toBeInTheDocument();
    expect(screen.getByText('Sign in')).toBeInTheDocument();
    expect(screen.queryByText('Logout')).not.toBeInTheDocument();
  });

  it('calls login function when login button is clicked', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
      login: mockLogin,
      logout: mockLogout,
    });

    render(<Toolbar />);

    fireEvent.click(screen.getByText('Sign in'));
    expect(mockLogin).toHaveBeenCalledTimes(1);
  });

  it('renders user info and logout button when user is authenticated', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        name: 'Test User',
        email: 'test@example.com',
        picture: 'https://example.com/pic.jpg',
      },
      loading: false,
      login: mockLogin,
      logout: mockLogout,
    });

    render(<Toolbar />);

    expect(screen.getByAltText('YouTube Logo')).toBeInTheDocument();
    expect(screen.getByAltText('Test User')).toBeInTheDocument();
    expect(screen.getByText('Logout')).toBeInTheDocument();
    expect(screen.queryByText('Sign in')).not.toBeInTheDocument();

    const img = screen.getByAltText('Test User');
    expect(img).toHaveAttribute('src', 'https://example.com/pic.jpg');
  });

  it('calls logout function when logout button is clicked', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        name: 'Test User',
        email: 'test@example.com',
        picture: 'https://example.com/pic.jpg',
      },
      loading: false,
      login: mockLogin,
      logout: mockLogout,
    });

    render(<Toolbar />);

    fireEvent.click(screen.getByText('Logout'));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it('uses fallback image on error', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        name: 'Test User',
        email: 'test@example.com',
        picture: 'https://invalid-url.com/pic.jpg',
      },
      loading: false,
      login: mockLogin,
      logout: mockLogout,
    });

    render(<Toolbar />);

    const img = screen.getByAltText('Test User');

    // Simulate error
    fireEvent.error(img);

    // After error, src should be the fallback
    // Since we hardcoded the fallback logic in component, we check if it changed
    // In our implementation: const fallbackImage = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(user?.name || 'User');
    expect(img).toHaveAttribute('src', 'https://ui-avatars.com/api/?name=Test%20User');
  });

  it('uses fallback image if user.picture is missing', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        name: 'Test User',
        email: 'test@example.com',
        picture: '',
      },
      loading: false,
      login: mockLogin,
      logout: mockLogout,
    });

    render(<Toolbar />);

    const img = screen.getByAltText('Test User');
    expect(img).toHaveAttribute('src', 'https://ui-avatars.com/api/?name=Test%20User');
  });
});
