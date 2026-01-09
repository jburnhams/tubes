import { render, screen, waitFor } from '@testing-library/react';
import { VideoPage } from '../../../src/pages/VideoPage';
import { YouTubeService } from '../../../src/services/youtube';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../../../src/context/AuthContext';
import { AuthService } from '../../../src/services/auth';

// Mock the YouTubeService
vi.mock('../../../src/services/youtube');

// Mock AuthService for AuthContext
vi.mock('../../../src/services/auth', () => ({
  AuthService: {
    checkAuth: vi.fn(),
    logout: vi.fn(),
    getLoginUrl: vi.fn(),
  },
}));

const mockVideoDetail = {
    youtube_id: 'rBYGGWgcJ4o',
    title: 'Peppa Pig Full Episodes',
    description: 'Watch FULL EPISODES Here',
    published_at: '2023-09-20T15:46:44Z',
    // Matches mockChannel.youtube_id
    channel_id: 'UCAOtE1V7Ots4DjM8JLlrYgg',
    thumbnail_url: 'https://i.ytimg.com/vi/rBYGGWgcJ4o/maxresdefault.jpg',
    duration: 'PT11H54M57S',
    raw_json: '{}',
    created_at: '2026-01-08T15:49:30.481Z',
    updated_at: '2026-01-08T15:49:30.481Z',
    duration_seconds: 42897,
    view_count: 128494,
    like_count: 410,
    comment_count: 0,
    best_thumbnail_url: 'https://i.ytimg.com/vi/rBYGGWgcJ4o/maxresdefault.jpg',
    best_thumbnail_width: 1280,
    best_thumbnail_height: 720,
    definition: 'hd',
    dimension: '2d',
    licensed_content: 1,
    caption: 0,
    privacy_status: 'public',
    embeddable: 1,
    made_for_kids: 1
};

const mockChannel = {
    youtube_id: 'UCAOtE1V7Ots4DjM8JLlrYgg',
    title: 'Peppa Pig - Official Channel',
    description: 'Welcome to the Official Peppa Pig channel!',
    custom_url: 'peppapig',
    thumbnail_url: 'https://example.com/channel.jpg',
    best_thumbnail_url: 'https://example.com/channel_high.jpg',
    published_at: '2013-10-09T00:00:00Z',
    country: 'GB'
};

const mockVideos = [
    {
        id: 'rec1',
        title: 'Recommended Video 1',
        description: 'Desc 1',
        thumbnail: 'https://example.com/rec1.jpg',
        duration_seconds: 300,
        channel_id: 'channel2',
        channel_title: 'Other Channel',
        channel_thumbnail: 'https://example.com/ch2.jpg',
        published_at: '2023-10-01T00:00:00Z',
        view_count: 5000
    },
    {
        id: 'rec2',
        title: 'Recommended Video 2',
        description: 'Desc 2',
        thumbnail: 'https://example.com/rec2.jpg',
        duration_seconds: 600,
        channel_id: 'channel3',
        channel_title: 'Another Channel',
        channel_thumbnail: 'https://example.com/ch3.jpg',
        published_at: '2023-10-02T00:00:00Z',
        view_count: 10000
    }
];

describe('VideoPage', () => {
    beforeEach(() => {
        vi.resetAllMocks();
        // Setup default auth behavior
        (AuthService.checkAuth as any).mockResolvedValue({
            id: 1,
            email: 'test@example.com',
            name: 'Test User',
            profile_picture: 'http://example.com/pic.jpg',
            is_admin: false,
            created_at: '2021-01-01',
            updated_at: '2021-01-01',
            last_login_at: '2021-01-01',
            session_id: 'test-session-id'
        });
    });

    it('fetches and displays video details, channel info, and recommendations', async () => {
        (YouTubeService.getVideo as any).mockResolvedValue(mockVideoDetail);
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: mockVideos });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [mockChannel] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/rBYGGWgcJ4o']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('Peppa Pig Full Episodes')).toBeInTheDocument();
        });

        // Main Video Info
        expect(screen.getByText(/128.5K views/)).toBeInTheDocument();
        expect(screen.getByText(/410/)).toBeInTheDocument(); // Likes

        // Channel Info
        expect(screen.getByText('Peppa Pig - Official Channel')).toBeInTheDocument();
        expect(screen.getByText('1.2M subscribers')).toBeInTheDocument();

        // Description
        expect(screen.getByText(/Watch FULL EPISODES Here/)).toBeInTheDocument();

        // Recommendations
        expect(screen.getByText('Recommended Video 1')).toBeInTheDocument();
        expect(screen.getByText('Recommended Video 2')).toBeInTheDocument();
        expect(screen.getByText('Other Channel')).toBeInTheDocument();

        expect(YouTubeService.getVideo).toHaveBeenCalledWith('rBYGGWgcJ4o');
        expect(YouTubeService.getVideos).toHaveBeenCalled();
        expect(YouTubeService.getChannels).toHaveBeenCalled();
    });

    it('shows error when fetch fails', async () => {
        const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        (YouTubeService.getVideo as any).mockRejectedValue(new Error('Failed to fetch'));
        // Mock others to resolve or reject, shouldn't matter as main fetch fails
        (YouTubeService.getVideos as any).mockResolvedValue({ videos: [] });
        (YouTubeService.getChannels as any).mockResolvedValue({ channels: [] });

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/rBYGGWgcJ4o']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('Failed to load video details.')).toBeInTheDocument();
        });

        consoleSpy.mockRestore();
    });
});
