import { render, screen, waitFor } from '@testing-library/react';
import { VideoGrid } from '@/src/components/VideoGrid';
import { YouTubeService } from '@/src/services/youtube';
import { vi, describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { BrowserRouter } from 'react-router-dom';

// Mock the YouTubeService
vi.mock('@/src/services/youtube');

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
    afterEach(() => {
        vi.useRealTimers();
    });

    it('renders loading state initially', () => {
        // Mock getVideos to return a promise that doesn't resolve immediately
        (YouTubeService.getVideos as any).mockImplementation(() => new Promise(() => {}));

        const { container } = render(<VideoGrid />);

        // Check for pulse animation which indicates loading
        expect(container.getElementsByClassName('animate-pulse').length).toBeGreaterThan(0);
    });

    it('renders videos after successful fetch', async () => {
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: mockVideos });

        render(
            <BrowserRouter>
                <VideoGrid />
            </BrowserRouter>
        );

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

    it('formats video metadata correctly (coverage for helpers)', async () => {
        // We create a diverse set of videos to hit all branches of helper functions
        const mockDate = new Date('2024-01-01T12:00:00Z');

        // Use fake timers to stabilize "now" but ensure we can run waitFor
        vi.useFakeTimers({ shouldAdvanceTime: true });
        vi.setSystemTime(mockDate);

        const diverseVideos = [
            // Views formatting
            { id: 'v1', title: 'V1', view_count: 500, published_at: '2024-01-01T11:59:50Z', duration_seconds: 50, thumbnail: 't1', channel_id: 'c1', channel_title: 'C1', channel_thumbnail: 'ct1' }, // 500 views, 10s ago, 0:50
            { id: 'v2', title: 'V2', view_count: 5000, published_at: '2024-01-01T11:55:00Z', duration_seconds: 3600, thumbnail: 't2', channel_id: 'c2', channel_title: 'C2', channel_thumbnail: 'ct2' }, // 5.0K views, 5m ago, 1:00:00
            { id: 'v3', title: 'V3', view_count: 1500000, published_at: '2024-01-01T09:00:00Z', duration_seconds: 3665, thumbnail: 't3', channel_id: 'c3', channel_title: 'C3', channel_thumbnail: 'ct3' }, // 1.5M views, 3h ago, 1:01:05

            // TimeAgo formatting additional branches
            { id: 'v4', title: 'V4', view_count: 0, published_at: '2023-12-29T12:00:00Z', duration_seconds: 0, thumbnail: 't4', channel_id: 'c4', channel_title: 'C4', channel_thumbnail: 'ct4' }, // 3 days ago
            { id: 'v5', title: 'V5', view_count: 0, published_at: '2023-10-01T12:00:00Z', duration_seconds: 0, thumbnail: 't5', channel_id: 'c5', channel_title: 'C5', channel_thumbnail: 'ct5' }, // 3 months ago
            { id: 'v6', title: 'V6', view_count: 0, published_at: '2022-01-01T12:00:00Z', duration_seconds: 0, thumbnail: 't6', channel_id: 'c6', channel_title: 'C6', channel_thumbnail: 'ct6' }, // 2 years ago
        ];

        (YouTubeService.getVideos as any).mockResolvedValue({ videos: diverseVideos });

        render(
            <BrowserRouter>
                <VideoGrid />
            </BrowserRouter>
        );

        await waitFor(() => {
            // View counts
            expect(screen.getByText((content) => content.includes('500 views'))).toBeInTheDocument();
            expect(screen.getByText((content) => content.includes('5.0K views'))).toBeInTheDocument();
            expect(screen.getByText((content) => content.includes('1.5M views'))).toBeInTheDocument();
        });

        await waitFor(() => {
             // Durations
            expect(screen.getByText('0:50')).toBeInTheDocument();
            expect(screen.getByText('1:00:00')).toBeInTheDocument();
            expect(screen.getByText('1:01:05')).toBeInTheDocument();
        });

        await waitFor(() => {
            // Time Ago
            expect(screen.getByText((content) => content.includes('10 seconds ago'))).toBeInTheDocument();
            expect(screen.getByText((content) => content.includes('5 minutes ago'))).toBeInTheDocument();
            expect(screen.getByText((content) => content.includes('3 hours ago'))).toBeInTheDocument();
            expect(screen.getByText((content) => content.includes('3 days ago'))).toBeInTheDocument();
            expect(screen.getByText((content) => content.includes('3 months ago'))).toBeInTheDocument();
            expect(screen.getByText((content) => content.includes('2 years ago'))).toBeInTheDocument();
        });
    });

    it('renders error message on fetch failure', async () => {
        (YouTubeService.getVideos as any).mockRejectedValue(new Error('Failed to fetch'));

        render(<VideoGrid />);

        await waitFor(() => {
            expect(screen.getByText('Failed to load videos. Please try again later.')).toBeInTheDocument();
        });
    });
});
