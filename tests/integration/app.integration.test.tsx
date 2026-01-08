import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../../src/App';
import { AuthProvider } from '../../src/context/AuthContext';
import { YouTubeService } from '../../src/services/youtube';
import { AuthService } from '../../src/services/auth';

// Mock YouTubeService
vi.mock('../../src/services/youtube', () => ({
  YouTubeService: {
    getChannels: vi.fn(),
  },
}));

// Mock AuthService
vi.mock('../../src/services/auth', () => {
  return {
    AuthService: {
      getCurrentUser: vi.fn().mockResolvedValue(null),
      login: vi.fn(),
      logout: vi.fn(),
    }
  };
});

const mockChannels = [
  {
    youtube_id: '1',
    name: 'Test Channel 1',
    picture: 'https://example.com/channel1.jpg',
  },
  {
    youtube_id: '2',
    name: 'Test Channel 2',
    picture: 'https://example.com/channel2.jpg',
  },
];

describe('App Integration', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });
    (AuthService.getCurrentUser as any).mockResolvedValue(null);
  });

  it('renders the app with all required elements', async () => {
    render(
      <AuthProvider>
        <App />
      </AuthProvider>
    );

    await waitFor(() => {
      // Sidebar navigation
      expect(screen.getByText('Home')).toBeInTheDocument();
      expect(screen.getByText('Explore')).toBeInTheDocument();
      expect(screen.getByText('Subscriptions')).toBeInTheDocument();

       // Toolbar elements
       expect(screen.getByAltText('YouTube Logo')).toBeInTheDocument();
       expect(screen.getByPlaceholderText('Search')).toBeInTheDocument();
       expect(screen.getByText('Sign in')).toBeInTheDocument();

        // Main content (VideoGrid)
        expect(screen.getByText('Talking Tech and AI with Google CEO Sundar Pichai!')).toBeInTheDocument();
        expect(screen.getByText('Marques Brownlee')).toBeInTheDocument();
    });
  });

  it('renders correct CSS classes for app structure', async () => {
     render(
      <AuthProvider>
        <App />
      </AuthProvider>
    );

    await waitFor(() => {
       const sidebar = screen.getByText('Home').closest('nav');
       expect(sidebar).toHaveClass('fixed left-0 bottom-0');

       const header = screen.getByAltText('YouTube Logo').closest('header');
       expect(header).toHaveClass('fixed top-0');
    });
  });

  it('renders login button when not authenticated', async () => {
    (AuthService.getCurrentUser as any).mockResolvedValue(null);

    render(
      <AuthProvider>
        <App />
      </AuthProvider>
    );

    await waitFor(() => {
        expect(screen.getByText('Sign in')).toBeInTheDocument();
    });
  });

  it('renders user profile and logout button when authenticated', async () => {
    const mockUser = { name: 'Test User', picture: 'https://example.com/pic.jpg', email: 'test@example.com' };
    (AuthService.getCurrentUser as any).mockResolvedValue(mockUser);

    render(
      <AuthProvider>
        <App />
      </AuthProvider>
    );

    await waitFor(() => {
        // Wait for loading to finish and user to be set
        expect(screen.getByAltText('Test User')).toBeInTheDocument();
    });

    // Check logout button (it might be hidden in dropdown but should exist)
    expect(screen.getByText('Logout')).toBeInTheDocument();

    expect(screen.queryByText('Sign in')).not.toBeInTheDocument();
  });

  it('fetches and displays subscriptions in the sidebar', async () => {
    render(
        <AuthProvider>
          <App />
        </AuthProvider>
      );

    await waitFor(() => {
        expect(YouTubeService.getChannels).toHaveBeenCalled();
    });

    await waitFor(() => {
        expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
        expect(screen.getByText('Test Channel 2')).toBeInTheDocument();
    });
  });
});
