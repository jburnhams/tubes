import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Sidebar } from '@/src/components/Sidebar';
import { YouTubeService } from '@/src/services/youtube';

// Mock YouTubeService
vi.mock('@/src/services/youtube', () => ({
  YouTubeService: {
    getChannels: vi.fn(),
  },
}));

describe('Sidebar Integration', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('toggles subscriptions list on click', async () => {
    const mockChannels = [
      { youtube_id: '1', title: 'Test Channel 1', thumbnail_url: 'url1' },
    ];
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });

    render(<Sidebar />);

    // Wait for channels to load and be displayed (initially expanded)
    await waitFor(() => {
      expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
    });

    // Find the toggle button (Subscriptions header)
    // The clickable part is the div with text "Subscriptions" and the arrow
    // The Sidebar component has multiple "Subscriptions" texts.
    // One is main nav, one is the section header.
    // The section header has "hidden md:block" container around it.
    // The toggle has "flex items-center px-6 py-2 cursor-pointer hover:bg-gray-100 justify-between group" class

    // Let's find by text "Subscriptions" but specifically the one that acts as a header.
    const subscriptionsElements = screen.getAllByText('Subscriptions');
    // The second one is likely the header (index 1), but let's be more robust.
    // The header is inside a div with onClick handler.
    // We can look for the channel list container which should appear/disappear.

    // Let's assume the second 'Subscriptions' is the toggle based on order in DOM.
    // Or we can find by class if we could query selector.
    // Let's try clicking the second 'Subscriptions'.
    const toggleButton = subscriptionsElements[1];

    fireEvent.click(toggleButton);

    // Should now be collapsed, so channel 1 should not be visible?
    // "Test Channel 1" might still be in DOM if hidden with CSS?
    // The code uses: {isSubscriptionsExpanded && ( ... )} so it should be removed from DOM.
    await waitFor(() => {
      expect(screen.queryByText('Test Channel 1')).not.toBeInTheDocument();
    });

    // Click again to expand
    fireEvent.click(toggleButton);

    await waitFor(() => {
      expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
    });
  });
});
