import { render, screen, waitFor } from '@testing-library/react';
import { VideoGrid } from '../../src/components/VideoGrid';
import { YouTubeService } from '../../src/services/youtube';
import { vi, describe, it, expect } from 'vitest';
import React from 'react';

// Mock the YouTubeService
vi.mock('../../src/services/youtube');

const mockVideos = [
    {
        id: '1',
        title: 'Test Video 1',
        description: 'Description 1',
        thumbnail: 'http://example.com/thumb1.jpg',
        duration_seconds: 120,
        channel_id: 'channel1',
        channel_title: 'Channel 1',
        channel_thumbnail: 'http://example.com/channel1.jpg',
        published_at: '2023-01-01T00:00:00Z',
        view_count: 1000
    },
    {
        id: '2',
        title: 'Test Video 2',
        description: 'Description 2',
        thumbnail: 'http://example.com/thumb2.jpg',
        duration_seconds: 3605, // 1h 0m 5s
        channel_id: 'channel2',
        channel_title: 'Channel 2',
        channel_thumbnail: 'http://example.com/channel2.jpg',
        published_at: '2023-01-02T00:00:00Z',
        view_count: 5000000
    }
];

describe('VideoGrid', () => {
    it('renders loading state initially', () => {
        // Mock getVideos to return a promise that doesn't resolve immediately
        (YouTubeService.getVideos as any).mockImplementation(() => new Promise(() => {}));

        const { container } = render(<VideoGrid />);

        // Check for pulse animation which indicates loading
        expect(container.getElementsByClassName('animate-pulse').length).toBeGreaterThan(0);
    });

    it('renders videos after successful fetch', async () => {
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: mockVideos });

        render(<VideoGrid />);

        await waitFor(() => {
            expect(screen.getByText('Test Video 1')).toBeInTheDocument();
            expect(screen.getByText('Test Video 2')).toBeInTheDocument();
        });

        // 'Channel 1' appears twice: once in the channel link and once in the tooltip
        expect(screen.getAllByText('Channel 1').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Channel 2').length).toBeGreaterThan(0);

        // Check formatting
        expect(screen.getByText('2:00')).toBeInTheDocument(); // 120s
        expect(screen.getByText('1:00:05')).toBeInTheDocument(); // 3605s

        // Use a text matcher function for views since they might be broken up by the separator
        expect(screen.getByText((content) => content.includes('1.0K views'))).toBeInTheDocument();
        expect(screen.getByText((content) => content.includes('5.0M views'))).toBeInTheDocument();
    });

    it('renders error message on fetch failure', async () => {
        (YouTubeService.getVideos as any).mockRejectedValue(new Error('Failed to fetch'));

        render(<VideoGrid />);

        await waitFor(() => {
            expect(screen.getByText('Failed to load videos. Please try again later.')).toBeInTheDocument();
        });
    });
});
