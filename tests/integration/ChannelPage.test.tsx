import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChannelPage } from '../../src/pages/ChannelPage';
import { YouTubeService } from '../../src/services/youtube';
import { ChannelDetail } from '../../src/types/youtube';

// Mock the YouTubeService
vi.mock('../../src/services/youtube', () => ({
  YouTubeService: {
    getChannel: vi.fn(),
    getVideos: vi.fn(),
  },
}));

describe('ChannelPage', () => {
  const mockChannel: ChannelDetail = {
    youtube_id: 'UC123',
    title: 'Test Channel',
    description: 'Test Description',
    custom_url: '@testchannel',
    thumbnail_url: 'http://example.com/small.jpg',
    best_thumbnail_url: 'http://example.com/large.jpg',
    published_at: '2023-01-01',
    country: 'US',
    view_count: 1000000,
    subscriber_count: 5000,
    video_count: 100,
    upload_playlist_id: 'UU123',
    best_thumbnail_width: 800,
    best_thumbnail_height: 800,
    raw_json: '{}',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    vi.mocked(YouTubeService.getChannel).mockReturnValue(new Promise(() => {})); // Never resolves

    const { container } = render(
      <MemoryRouter initialEntries={['/channel/UC123']}>
        <Routes>
          <Route path="/channel/:id" element={<ChannelPage />} />
        </Routes>
      </MemoryRouter>
    );

    // Check for spinner class or structure
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  it('renders channel details after fetch', async () => {
    vi.mocked(YouTubeService.getChannel).mockResolvedValue(mockChannel);
    vi.mocked(YouTubeService.getVideos).mockResolvedValue({ videos: [] });

    render(
      <MemoryRouter initialEntries={['/channel/UC123']}>
        <Routes>
          <Route path="/channel/:id" element={<ChannelPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Channel')).toBeInTheDocument();
    });

    expect(screen.getByText('@testchannel')).toBeInTheDocument();
    expect(screen.getByText(/5.0K subscribers/)).toBeInTheDocument(); // formatCount(5000) -> 5.0K
    expect(screen.getByText(/100 videos/)).toBeInTheDocument();
    expect(screen.getByText(/1.0M views/)).toBeInTheDocument(); // formatCount(1000000) -> 1.0M
    expect(screen.getByText('Test Description')).toBeInTheDocument();
    expect(screen.getByAltText('Test Channel')).toHaveAttribute('src', 'http://example.com/large.jpg');
    // Verify banner
    expect(screen.getByAltText('Test Channel banner')).toHaveAttribute('src', 'http://example.com/large.jpg');
  });

  it('renders error message on failure', async () => {
    vi.mocked(YouTubeService.getChannel).mockRejectedValue(new Error('Failed to fetch'));

    render(
      <MemoryRouter initialEntries={['/channel/UC123']}>
        <Routes>
          <Route path="/channel/:id" element={<ChannelPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Failed to load channel details.')).toBeInTheDocument();
    });
  });
});
