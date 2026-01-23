import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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

  it('renders static navigation items with correct links', async () => {
    // Mock getChannels to resolve immediately
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );

    // helper to check link href
    const checkLink = (text: string, href: string) => {
      const link = screen.getByText(text).closest('a');
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', href);
    };

    checkLink('Home', '/');
    checkLink('Explore', '/channels');
    checkLink('Originals', '/channels');
    checkLink('Music', '/channels');
    checkLink('Library', '/channels');

    // 'Subscriptions' header is present (not a link itself, but part of the layout)
    expect(screen.getAllByText('Subscriptions').length).toBeGreaterThan(0);

    // Wait for effect to settle to avoid act warnings
    await waitFor(() => {
      expect(YouTubeService.getChannels).toHaveBeenCalled();
    });
  });

  it('calls getChannels on mount', async () => {
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );

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

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
      expect(screen.getByText('Test Channel 2')).toBeInTheDocument();
    });
  });

  it('handles fetch error', async () => {
    (YouTubeService.getChannels as any).mockRejectedValue(new Error('Failed'));
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => { });

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Failed to load channels.')).toBeInTheDocument();
    });

    consoleSpy.mockRestore();
  });
});
