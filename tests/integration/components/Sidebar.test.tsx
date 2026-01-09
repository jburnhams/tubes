import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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

describe('Sidebar Integration', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('toggles subscriptions list on click', async () => {
    const mockChannels = [
      { youtube_id: '1', title: 'Test Channel 1', thumbnail_url: 'url1' },
    ];
    (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );

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
    // There is only one text "Subscriptions" in the rendered sidebar (the header).
    // The other one is in the alt text of the image, which getByText ignores.
    const toggleButton = screen.getByText('Subscriptions');

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
