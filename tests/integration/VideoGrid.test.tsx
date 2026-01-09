import { render, screen, waitFor } from '@testing-library/react';
import { VideoGrid } from '../../src/components/VideoGrid';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest';
import React from 'react';

const server = setupServer(
    http.get('https://storage.jonathanburnhams.com/api/youtube/videos/random', () => {
        return HttpResponse.json({
            videos: [
                {
                    id: '1',
                    title: 'Integration Test Video',
                    description: 'Description 1',
                    thumbnail: 'http://example.com/thumb1.jpg',
                    duration_seconds: 120,
                    channel_id: 'channel1',
                    channel_title: 'Integration Channel',
                    channel_thumbnail: 'http://example.com/channel1.jpg',
                    published_at: '2023-01-01T00:00:00Z',
                    view_count: 1000
                }
            ]
        });
    })
);

describe('VideoGrid Integration', () => {
    beforeAll(() => server.listen());
    afterEach(() => server.resetHandlers());
    afterAll(() => server.close());

    it('fetches and displays videos using MSW', async () => {
        render(<VideoGrid />);

        await waitFor(() => {
            expect(screen.getByText('Integration Test Video')).toBeInTheDocument();
        });

        expect(screen.getAllByText('Integration Channel').length).toBeGreaterThan(0);
        expect(screen.getByText('2:00')).toBeInTheDocument();
        expect(screen.getByText((content) => content.includes('1.0K views'))).toBeInTheDocument();
    });

    it('handles server errors', async () => {
        server.use(
            http.get('https://storage.jonathanburnhams.com/api/youtube/videos/random', () => {
                return new HttpResponse(null, { status: 500 });
            })
        );

        render(<VideoGrid />);

        await waitFor(() => {
            expect(screen.getByText('Failed to load videos. Please try again later.')).toBeInTheDocument();
        });
    });
});
