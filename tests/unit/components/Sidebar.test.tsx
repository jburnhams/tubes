import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Sidebar } from '@/src/components/Sidebar';
import { YouTubeService } from '@/src/services/youtube';

// Mock YouTubeService
vi.mock('@/src/services/youtube', () => ({
  YouTubeService: {
    getChannels: vi.fn(),
  },
}));

describe('Sidebar', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders static navigation items', async () => {
    // Mock getChannels to resolve immediately
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

    render(<Sidebar />);

    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Explore')).toBeInTheDocument();
    // 'Subscriptions' appears twice (once in main nav, once in sidebar section header)
    expect(screen.getAllByText('Subscriptions').length).toBeGreaterThan(0);
    expect(screen.getByText('Originals')).toBeInTheDocument();
    expect(screen.getByText('Music')).toBeInTheDocument();
    expect(screen.getByText('Library')).toBeInTheDocument();

    // Wait for effect to settle to avoid act warnings
    await waitFor(() => {
        expect(YouTubeService.getChannels).toHaveBeenCalled();
    });
  });

  it('calls getChannels on mount', async () => {
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

    render(<Sidebar />);

    await waitFor(() => {
      expect(YouTubeService.getChannels).toHaveBeenCalledTimes(1);
    });
  });

  it('renders fetched channels', async () => {
    const mockChannels = [
      { youtube_id: '1', title: 'Test Channel 1', thumbnail_url: 'url1' },
      { youtube_id: '2', title: 'Test Channel 2', thumbnail_url: 'url2' },
    ];
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });

    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
      expect(screen.getByText('Test Channel 2')).toBeInTheDocument();
    });
  });

  it('handles fetch error', async () => {
    (YouTubeService.getChannels as any).mockRejectedValue(new Error('Failed'));
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<Sidebar />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load channels.')).toBeInTheDocument();
    });

    consoleSpy.mockRestore();
  });
});
