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

  it('keeps subscriptions list expanded', async () => {
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

    // Find the Subscriptions header
    const toggleButton = screen.getByText('Subscriptions');

    fireEvent.click(toggleButton);

    // Should NOT be collapsed. Channels should still be visible.
    await waitFor(() => {
      expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
    });

    // Verify it remains visible (redundant but confirming "always open")
    fireEvent.click(toggleButton);
    await waitFor(() => {
      expect(screen.getByText('Test Channel 1')).toBeInTheDocument();
    });
  });
});
