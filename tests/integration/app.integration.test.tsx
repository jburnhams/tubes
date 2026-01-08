import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as fs from 'fs';
import * as path from 'path';
import App from '@/src/App';
import { vi, Mock } from 'vitest';
import * as AuthContext from '@/src/context/AuthContext';
import { YouTubeService } from '@/src/services/youtube';

// Mock the AuthContext
vi.mock('@/src/context/AuthContext', () => ({
  useAuth: vi.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Mock YouTubeService
vi.mock('@/src/services/youtube', () => ({
  YouTubeService: {
    getChannels: vi.fn(),
  },
}));

describe('Browser Integration Tests', () => {
  // Default mock implementation
  const mockUseAuth = AuthContext.useAuth as Mock;
  const mockChannels = [
    {
      youtube_id: '1',
      title: 'Test Channel 1',
      description: 'Desc 1',
      custom_url: '@channel1',
      thumbnail_url: 'url1',
      best_thumbnail_url: null,
      published_at: '2023-01-01',
      country: 'US',
    },
  ];

  beforeEach(() => {
    vi.resetAllMocks();
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
    });

    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });
  });

  describe('index.html structure', () => {
    let htmlContent: string;

    beforeEach(() => {
      htmlContent = fs.readFileSync(
        path.join(__dirname, '..', '..', 'index.html'),
        'utf-8'
      );
    });

    it('has valid HTML structure with doctype', () => {
      expect(htmlContent).toMatch(/^<!doctype html>/i);
    });

    it('has correct language attribute', () => {
      expect(htmlContent).toMatch(/<html[^>]+lang="en"/i);
    });

    it('has required meta tags', () => {
      expect(htmlContent).toMatch(/<meta\s+charset="UTF-8"\s*\/?>/i);
      expect(htmlContent).toMatch(/<meta\s+name="viewport"\s+content="[^"]*width=device-width[^"]*"\s*\/?>/i);
    });

    it('has a title element', () => {
      const titleMatch = htmlContent.match(/<title>([^<]+)<\/title>/i);
      expect(titleMatch).toBeTruthy();
      expect(titleMatch?.[1]).toBeTruthy();
      expect(titleMatch?.[1].length).toBeGreaterThan(0);
    });

    it('has root div with correct id', () => {
      expect(htmlContent).toMatch(/<div\s+id="root"[^>]*>/i);
    });

    it('has main script tag pointing to correct entry point', () => {
      expect(htmlContent).toMatch(/<script\s+type="module"\s+src="\/src\/main\.tsx"[^>]*>/i);
    });

    it('has favicon link', () => {
      expect(htmlContent).toMatch(/<link\s+rel="icon"/i);
    });

    it('has proper HTML5 structure', () => {
      // Check for essential HTML5 elements
      expect(htmlContent).toContain('<head>');
      expect(htmlContent).toContain('</head>');
      expect(htmlContent).toContain('<body>');
      expect(htmlContent).toContain('</body>');
      expect(htmlContent).toContain('</html>');
    });
  });

  describe('App component integration', () => {
    it('renders the app with all required elements', async () => {
      render(<App />);

      // Check main heading - fix for multiple 'Tubes' text (Logo + H1)
      const tubesElements = screen.getAllByText('Tubes');
      expect(tubesElements.length).toBeGreaterThanOrEqual(1);

      // Check description
      expect(
        screen.getByText(/Discover your favorite YouTube channels/i)
      ).toBeInTheDocument();

      // Check grid loads
      await waitFor(() => {
        expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
      });
    });

    it('renders channel modal when card is clicked', async () => {
      const user = userEvent.setup();
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Test Channel 1'));

      expect(screen.getByTestId('channel-modal-content')).toBeInTheDocument();
    });

    it('renders correct CSS classes for app structure', async () => {
      const { container } = render(<App />);

      const appDiv = container.querySelector('.app');
      expect(appDiv).toBeInTheDocument();

      // Wait for grid to render
      await waitFor(() => {
        expect(container.querySelector('.grid')).toBeInTheDocument();
      });
    });
  });

  describe('Authentication Integration', () => {
    it('renders login button when not authenticated', () => {
      // mockUseAuth is already set to return user: null in beforeEach
      render(<App />);

      expect(screen.getByText('Login')).toBeInTheDocument();
      expect(screen.queryByText('Logout')).not.toBeInTheDocument();
    });

    it('renders user profile and logout button when authenticated', () => {
      const mockUseAuth = AuthContext.useAuth as Mock;
      mockUseAuth.mockReturnValue({
        user: {
          id: 1,
          name: 'Test User',
          email: 'test@example.com',
          picture: 'https://example.com/pic.jpg',
        },
        loading: false,
        error: null,
        login: vi.fn(),
        logout: vi.fn(),
      });

      render(<App />);

      // "Welcome, " was removed in the new Toolbar design, just showing name
      expect(screen.getByText('Test User')).toBeInTheDocument();
      expect(screen.getByText('Logout')).toBeInTheDocument();
      expect(screen.queryByText('Login')).not.toBeInTheDocument();

      const img = screen.getByAltText('Test User');
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute('src', 'https://example.com/pic.jpg');
    });
  });

  describe('Full page rendering simulation', () => {
    it('simulates complete page load and interaction flow', async () => {
      const user = userEvent.setup();

      // Verify index.html exists and has root element
      const html = fs.readFileSync(
        path.join(__dirname, '..', '..', 'index.html'),
        'utf-8'
      );
      expect(html).toContain('id="root"');

      // Render the React app in jsdom environment (simulating what main.tsx does)
      render(<App />);

      // Verify initial state
      const tubesElements = screen.getAllByText('Tubes');
      expect(tubesElements.length).toBeGreaterThanOrEqual(1);

      // Simulate user workflow
      await waitFor(() => {
        expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Test Channel 1'));
      expect(screen.getByTestId('channel-modal-content')).toBeInTheDocument();

      const closeButton = screen.getByLabelText('Close modal');
      await user.click(closeButton);

      await waitFor(() => {
        expect(screen.queryByTestId('channel-modal-content')).not.toBeInTheDocument();
      });
    });
  });
});
