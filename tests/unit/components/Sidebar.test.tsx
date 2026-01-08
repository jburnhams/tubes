import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Sidebar } from '../../../src/components/Sidebar';
import { YouTubeService } from '../../../src/services/youtube';

// Mock YouTubeService
vi.mock('../../../src/services/youtube', () => ({
  YouTubeService: {
    getChannels: vi.fn(),
  },
}));

const mockChannels = [
  {
    youtube_id: '1',
    title: 'Channel A',
    thumbnail_url: 'https://example.com/a.jpg',
  },
  {
    youtube_id: '2',
    title: 'Channel B',
    thumbnail_url: 'https://example.com/b.jpg',
  },
];

describe('Sidebar', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });
  });

  it('renders navigation items', async () => {
    render(<Sidebar />);
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Explore')).toBeInTheDocument();

    const subs = screen.getAllByText('Subscriptions');
    expect(subs.length).toBeGreaterThanOrEqual(1);
  });

  it('fetches and displays channels initially (since expanded by default)', async () => {
    render(<Sidebar />);

    await waitFor(() => {
        expect(screen.getByText('Channel A')).toBeInTheDocument();
        expect(screen.getByText('Channel B')).toBeInTheDocument();
    });
  });

  it('toggles channels visibility when header is clicked', async () => {
    render(<Sidebar />);

    // Wait for channels to load
    await waitFor(() => {
        expect(screen.getByText('Channel A')).toBeInTheDocument();
    });

    // Click the subscriptions header
    const subHeader = screen.getAllByText('Subscriptions')[0];
    fireEvent.click(subHeader);

    // Channels should be hidden
    await waitFor(() => {
        expect(screen.queryByText('Channel A')).not.toBeInTheDocument();
    });

    // Click again to show
    fireEvent.click(subHeader);

    await waitFor(() => {
        expect(screen.getByText('Channel A')).toBeInTheDocument();
    });
  });
});
