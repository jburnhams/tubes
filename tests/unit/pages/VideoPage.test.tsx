import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { VideoPage } from '../../../src/pages/VideoPage';
import { YouTubeService } from '../../../src/services/youtube';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../../../src/context/AuthContext';
import { AuthService } from '../../../src/services/auth';

// Mock Services
vi.mock('../../../src/services/youtube');
vi.mock('../../../src/services/auth', () => ({
    AuthService: {
        checkAuth: vi.fn(),
        logout: vi.fn(),
        getLoginUrl: vi.fn(),
    },
}));

// Mock TubePlayerWrapper to avoid Shaka player issues in JSDOM
vi.mock('../../../src/components/TubePlayerWrapper', () => ({
    TubePlayerWrapper: () => <div data-testid="tube-player">Player Placeholder</div>
}));

describe('VideoPage Unit Tests', () => {
    const mockDate = new Date('2024-01-01T12:00:00Z');

    beforeEach(() => {
        vi.resetAllMocks();
        vi.useFakeTimers({ shouldAdvanceTime: true });
        vi.setSystemTime(mockDate);

        // Default Auth Mock
        (AuthService.checkAuth as any).mockResolvedValue({
            id: 1,
            user: { id: 1, name: 'Test User' }
        });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    const createVideo = (overrides: any = {}) => ({
        youtube_id: 'vid1',
        title: 'Test Video',
        description: 'Test Description',
        published_at: '2024-01-01T11:59:00Z', // 1 min ago
        channel_id: 'ch1',
        thumbnail_url: 'thumb.jpg',
        duration_seconds: 60,
        view_count: 100,
        like_count: 10,
        comment_count: 5,
        ...overrides
    });

    const createChannel = (overrides: any = {}) => ({
        youtube_id: 'ch1',
        title: 'Test Channel',
        thumbnail_url: 'ch_thumb.jpg',
        ...overrides
    });

    it('renders and formats various view counts correctly', async () => {
        // Test < 1K, > 1K, > 1M
        const videoLow = createVideo({ youtube_id: 'low', view_count: 500, like_count: 500 });

        (YouTubeService.getVideo as any).mockResolvedValue(videoLow);
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: [] });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/low']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText(/500 views/)).toBeInTheDocument();
            expect(screen.getByText('500')).toBeInTheDocument(); // Likes
        });
    });

    it('formats K and M view counts', async () => {
        const videoHigh = createVideo({
            youtube_id: 'high',
            view_count: 1500000, // 1.5M
            like_count: 2500 // 2.5K
        });

        (YouTubeService.getVideo as any).mockResolvedValue(videoHigh);
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: [] });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/high']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText(/1.5M views/)).toBeInTheDocument();
            expect(screen.getByText('2.5K')).toBeInTheDocument(); // Likes
        });
    });

    it('formats durations correctly (minutes vs hours)', async () => {
        // Recommendation with > 1 hour and < 1 hour
        const recs = [
            { id: 'r1', title: 'Long', duration_seconds: 3661, thumbnail: '', published_at: mockDate.toISOString(), view_count: 0, channel_title: 'C', channel_id: 'c' }, // 1:01:01
            { id: 'r2', title: 'Short', duration_seconds: 65, thumbnail: '', published_at: mockDate.toISOString(), view_count: 0, channel_title: 'C', channel_id: 'c' }    // 1:05
        ];

        const mainVideo = createVideo();

        (YouTubeService.getVideo as any).mockResolvedValue(mainVideo);
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: recs });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/vid1']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('1:01:01')).toBeInTheDocument();
            expect(screen.getByText('1:05')).toBeInTheDocument();
        });
    });

    it('formats relative time correctly for all intervals', async () => {
        // We need multiple recommendations to test all branches of timeAgo
        // Current time is 2024-01-01T12:00:00Z
        const recs = [
            { id: '1', title: 'Years', published_at: '2022-01-01T12:00:00Z', view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' }, // 2 years
            { id: '2', title: 'Months', published_at: '2023-10-01T12:00:00Z', view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' }, // 3 months
            { id: '3', title: 'Days', published_at: '2023-12-29T12:00:00Z', view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' }, // 3 days
            { id: '4', title: 'Hours', published_at: '2024-01-01T09:00:00Z', view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' }, // 3 hours
            { id: '5', title: 'Minutes', published_at: '2024-01-01T11:55:00Z', view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' }, // 5 minutes
            { id: '6', title: 'Seconds', published_at: '2024-01-01T11:59:50Z', view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' }, // 10 seconds
        ];

        (YouTubeService.getVideo as any).mockResolvedValue(createVideo());
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: recs });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/vid1']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText(/2 years ago/)).toBeInTheDocument();
            expect(screen.getByText(/3 months ago/)).toBeInTheDocument();
            expect(screen.getByText(/3 days ago/)).toBeInTheDocument();
            expect(screen.getByText(/3 hours ago/)).toBeInTheDocument();
            expect(screen.getByText(/5 minutes ago/)).toBeInTheDocument();
            expect(screen.getByText(/10 seconds ago/)).toBeInTheDocument();
        });
    });

    it('handles unknown channel scenario', async () => {
        const video = createVideo({ channel_id: 'unknown_ch' });
        // Channel list does not contain 'unknown_ch'
        (YouTubeService.getVideo as any).mockResolvedValue(video);
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: [] });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [createChannel({ youtube_id: 'other' })] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/vid1']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('Unknown Channel')).toBeInTheDocument();
            expect(screen.getByText('?')).toBeInTheDocument(); // Placeholder avatar
        });
    });

    it('toggles description expansion', async () => {
        (YouTubeService.getVideo as any).mockResolvedValue(createVideo());
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: [] });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/vid1']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        // Initially expanded, so "Show less" should be visible
        await waitFor(() => {
            expect(screen.getByText('Show less')).toBeInTheDocument();
            expect(screen.queryByText('Show more')).not.toBeInTheDocument();
        });

        // Click to collapse
        fireEvent.click(screen.getByText('Show less').closest('div')!.parentElement!);

        expect(screen.getByText('Show more')).toBeInTheDocument();
        expect(screen.queryByText('Show less')).not.toBeInTheDocument();

        // Click to expand again
        fireEvent.click(screen.getByText('Show more').closest('div')!.parentElement!);

        expect(screen.getByText('Show less')).toBeInTheDocument();
    });

    it('filters current video from recommendations', async () => {
        const video = createVideo({ youtube_id: 'current' });
        const recs = [
            { id: 'current', title: 'Same Video', thumbnail: '', published_at: mockDate.toISOString(), view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' },
            { id: 'other', title: 'Other Video', thumbnail: '', published_at: mockDate.toISOString(), view_count: 0, duration_seconds: 0, channel_title: 'C', channel_id: 'c' }
        ];

        (YouTubeService.getVideo as any).mockResolvedValue(video);
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: recs });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/current']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('Other Video')).toBeInTheDocument();
            expect(screen.queryByText('Same Video')).not.toBeInTheDocument();
        });
    });
});
