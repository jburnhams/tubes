import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ChannelGrid } from '@/src/components/ChannelGrid';
import { YouTubeService } from '@/src/services/youtube';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock YouTubeService
vi.mock('@/src/services/youtube', () => ({
  YouTubeService: {
    getChannels: vi.fn(),
  },
}));

const mockChannels = [
  {
    youtube_id: '1',
    title: 'Channel 1',
    description: 'Desc 1',
    custom_url: '@channel1',
    thumbnail_url: 'url1',
    best_thumbnail_url: null,
    published_at: '2023-01-01',
    country: 'US',
  },
  {
    youtube_id: '2',
    title: 'Channel 2',
    description: 'Desc 2',
    custom_url: '@channel2',
    thumbnail_url: 'url2',
    best_thumbnail_url: null,
    published_at: '2023-01-02',
    country: 'UK',
  },
];

describe('ChannelGrid', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows loading state initially', async () => {
    (YouTubeService.getChannels as any).mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<ChannelGrid />);
    // Check for spinner or loading text (currently strictly styling, checking structure might be brittle)
    // But implementation has a specific spinner structure
    const spinner = document.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  it('renders channels after fetching', async () => {
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });
    render(<ChannelGrid />);

    await waitFor(() => {
      expect(screen.getByText('Channel 1')).toBeInTheDocument();
      expect(screen.getByText('Channel 2')).toBeInTheDocument();
    });
  });

  it('shows error message on failure', async () => {
    (YouTubeService.getChannels as any).mockRejectedValue(new Error('Failed'));
    render(<ChannelGrid />);

    await waitFor(() => {
      expect(screen.getByText(/Failed to load channels/i)).toBeInTheDocument();
    });
  });

  it('opens modal when channel is clicked', async () => {
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });
    render(<ChannelGrid />);

    await waitFor(() => {
      expect(screen.getByText('Channel 1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Channel 1'));

    expect(screen.getByTestId('channel-modal-content')).toBeInTheDocument();
    expect(screen.getAllByText('Channel 1').length).toBeGreaterThan(1); // One in card, one in modal
  });
});
