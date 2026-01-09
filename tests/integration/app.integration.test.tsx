import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import App from '../../src/App';
import { AuthProvider } from '../../src/context/AuthContext';
import { YouTubeService } from '../../src/services/youtube';
import { AuthService } from '../../src/services/auth';

// Mock YouTubeService
vi.mock('../../src/services/youtube', () => ({
  YouTubeService: {
    getChannels: vi.fn(),
    getVideos: vi.fn(),
  },
}));

// Mock AuthService
vi.mock('../../src/services/auth', () => {
  return {
    AuthService: {
      checkAuth: vi.fn(),
      getLoginUrl: vi.fn(),
      logout: vi.fn(),
    }
  };
});

const mockChannels = [
  {
    youtube_id: '1',
    title: 'Test Channel 1',
    thumbnail_url: 'https://example.com/channel1.jpg',
  },
  {
    youtube_id: '2',
    title: 'Test Channel 2',
    thumbnail_url: 'https://example.com/channel2.jpg',
  },
];

const mockVideos = [
    {
        id: '1',
        title: 'Talking Tech and AI with Google CEO Sundar Pichai!',
        description: 'Description 1',
        thumbnail: 'http://example.com/thumb1.jpg',
        duration_seconds: 120,
        channel_id: 'channel1',
        channel_title: 'Marques Brownlee',
        channel_thumbnail: 'http://example.com/channel1.jpg',
        published_at: '2023-01-01T00:00:00Z',
        view_count: 1000
    }
];

describe('App Integration', () => {
  // Mock console.error to avoid noise in tests where we expect errors
  const originalConsoleError = console.error;

  beforeEach(() => {
    vi.resetAllMocks();
    console.error = vi.fn();
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });
    (YouTubeService.getVideos as any).mockResolvedValue(mockVideos);

    // Default to unauthenticated (rejecting auth check)
    // We use mockImplementation to ensure it returns a fresh promise each time if needed
    (AuthService.checkAuth as any).mockRejectedValue(new Error('Auth failed'));
  });

  afterEach(() => {
    console.error = originalConsoleError;
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
      expect(screen.getAllByText('Subscriptions')[0]).toBeInTheDocument();

       // Toolbar elements
       expect(screen.getByAltText('YouTube Logo')).toBeInTheDocument();
       expect(screen.getByPlaceholderText('Search')).toBeInTheDocument();
       expect(screen.getByText('Sign in')).toBeInTheDocument();

        // Main content (VideoGrid)
        expect(screen.getByText('Talking Tech and AI with Google CEO Sundar Pichai!')).toBeInTheDocument();
        expect(screen.getAllByText('Marques Brownlee')[0]).toBeInTheDocument();
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
    // Already set to reject in beforeEach
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
    const mockUser = { id: 1, name: 'Test User', picture: 'https://example.com/pic.jpg', email: 'test@example.com' };

    // Override the mock for this specific test
    // We use mockResolvedValue which should take precedence
    (AuthService.checkAuth as any).mockResolvedValue(mockUser);

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
