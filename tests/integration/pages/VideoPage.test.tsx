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

    it('fetches and displays video details', async () => {
        (YouTubeService.getVideo as any).mockResolvedValue(mockVideoDetail);

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/video/rBYGGWgcJ4o']}>
                    <Routes>
                        <Route path="/video/:id" element={<VideoPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        // Check for loading state (spinners usually have role="status" or class matching loader)
        // In our component it's a div with animate-spin class.
        // We can check if it disappears or just wait for content.

        await waitFor(() => {
            expect(screen.getByText('Peppa Pig Full Episodes')).toBeInTheDocument();
        });

        expect(screen.getByText(/128,494 views/)).toBeInTheDocument();
        expect(screen.getByText(/Watch FULL EPISODES Here/)).toBeInTheDocument();
        expect(screen.getByText(/410/)).toBeInTheDocument(); // Likes

        // TubePlayerWrapper should be rendered instead of image if ID is present
        // Since we are mocking TubePlayerWrapper indirectly (TubePlayer class), we check that the image is NOT present
        // Wait, if TubePlayerWrapper is used, the image is NOT rendered.
        // The test previously checked for the image:
        // const img = screen.getByAltText('Peppa Pig Full Episodes');
        // expect(img).toHaveAttribute('src', 'https://i.ytimg.com/vi/rBYGGWgcJ4o/maxresdefault.jpg');

        // Now that we have the player, the image placeholder is replaced.
        // We should verify that.
        const img = screen.queryByAltText('Peppa Pig Full Episodes');
        expect(img).not.toBeInTheDocument();

        expect(YouTubeService.getVideo).toHaveBeenCalledWith('rBYGGWgcJ4o');
    });

    it('shows error when fetch fails', async () => {
        (YouTubeService.getVideo as any).mockRejectedValue(new Error('Failed to fetch'));

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
    });
});
