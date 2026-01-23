import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChannelsPage } from '@/src/pages/ChannelsPage';
import { YouTubeService } from '@/src/services/youtube';

// Mock YouTubeService
vi.mock('@/src/services/youtube', () => ({
    YouTubeService: {
        getChannels: vi.fn(),
    },
}));

describe('ChannelsPage', () => {
    beforeEach(() => {
        vi.resetAllMocks();
    });

    it('renders loading state initially', async () => {
        // Mock getChannels to return a promise that doesn't resolve immediately
        (YouTubeService.getChannels as any).mockImplementation(() => new Promise(() => { }));

        render(
            <MemoryRouter>
                <ChannelsPage />
            </MemoryRouter>
        );

        // Look for loading spinner or container
        const spinner = document.querySelector('.animate-spin');
        expect(spinner).toBeInTheDocument();
    });

    it('renders channels when data is loaded', async () => {
        const mockChannels = [
            { youtube_id: '1', title: 'Channel One', thumbnail_url: 'thumb1.jpg', description: 'Desc 1' },
            { youtube_id: '2', title: 'Channel Two', thumbnail_url: 'thumb2.jpg', description: 'Desc 2' },
        ];
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: mockChannels });

        render(
            <MemoryRouter>
                <ChannelsPage />
            </MemoryRouter>
        );

        await waitFor(() => {
            expect(screen.getByText('Channel One')).toBeInTheDocument();
            expect(screen.getByText('Channel Two')).toBeInTheDocument();
        });

        // Check for images
        const images = screen.getAllByRole('img');
        expect(images.length).toBeGreaterThanOrEqual(2);
        expect(images[0]).toHaveAttribute('src', 'thumb1.jpg');
    });

    it('renders error state on fetch failure', async () => {
        (YouTubeService.getChannels as any).mockRejectedValue(new Error('API Error'));
        const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => { });

        render(
            <MemoryRouter>
                <ChannelsPage />
            </MemoryRouter>
        );

        await waitFor(() => {
            expect(screen.getByText(/Failed to load channels/i)).toBeInTheDocument();
        });

        consoleSpy.mockRestore();
    });

    it('renders empty state when no channels found', async () => {
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <MemoryRouter>
                <ChannelsPage />
            </MemoryRouter>
        );

        await waitFor(() => {
            expect(screen.getByText(/No channels found/i)).toBeInTheDocument();
        });
    });
});
