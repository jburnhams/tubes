import { render, screen, waitFor } from '@testing-library/react';
import { VideoPage } from '../../../src/pages/VideoPage';
import { YouTubeService } from '../../../src/services/youtube';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// Mock the YouTubeService
vi.mock('../../../src/services/youtube');

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
    });

    it('fetches and displays video details', async () => {
        (YouTubeService.getVideo as any).mockResolvedValue(mockVideoDetail);

        render(
            <MemoryRouter initialEntries={['/video/rBYGGWgcJ4o']}>
                <Routes>
                    <Route path="/video/:id" element={<VideoPage />} />
                </Routes>
            </MemoryRouter>
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

        // Check thumbnail
        const img = screen.getByAltText('Peppa Pig Full Episodes');
        expect(img).toHaveAttribute('src', 'https://i.ytimg.com/vi/rBYGGWgcJ4o/maxresdefault.jpg');

        expect(YouTubeService.getVideo).toHaveBeenCalledWith('rBYGGWgcJ4o');
    });

    it('shows error when fetch fails', async () => {
        (YouTubeService.getVideo as any).mockRejectedValue(new Error('Failed to fetch'));

        render(
            <MemoryRouter initialEntries={['/video/rBYGGWgcJ4o']}>
                <Routes>
                    <Route path="/video/:id" element={<VideoPage />} />
                </Routes>
            </MemoryRouter>
        );

        await waitFor(() => {
            expect(screen.getByText('Failed to load video details.')).toBeInTheDocument();
        });
    });
});
