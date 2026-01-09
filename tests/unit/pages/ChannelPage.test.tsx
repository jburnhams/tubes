import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChannelPage } from '../../../src/pages/ChannelPage';
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

// Mock TubePlayerWrapper if used (not in ChannelPage but good practice)
vi.mock('../../../src/components/TubePlayerWrapper', () => ({
  TubePlayerWrapper: () => <div data-testid="tube-player">Player Placeholder</div>
}));

// Mock VideoGrid
vi.mock('../../../src/components/VideoGrid', () => ({
  VideoGrid: () => <div data-testid="video-grid">VideoGrid Placeholder</div>
}));

describe('ChannelPage Unit Tests', () => {
    beforeEach(() => {
        vi.resetAllMocks();

        // Default Auth Mock
        (AuthService.checkAuth as any).mockResolvedValue({
            id: 1,
            user: { id: 1, name: 'Test User' }
        });
    });

    const createChannel = (overrides: any = {}) => ({
        youtube_id: 'ch1',
        title: 'Test Channel',
        description: 'Test Description',
        custom_url: '@testchannel',
        subscriber_count: 1000,
        video_count: 50,
        view_count: 5000,
        thumbnail_url: 'thumb.jpg',
        best_thumbnail_url: 'best_thumb.jpg',
        published_at: '2020-01-01T00:00:00Z',
        ...overrides
    });

    it('renders channel details correctly', async () => {
        const channel = createChannel();
        (YouTubeService.getChannel as any).mockResolvedValue(channel);

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/channel/ch1']}>
                    <Routes>
                        <Route path="/channel/:id" element={<ChannelPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('Test Channel')).toBeInTheDocument();
            expect(screen.getByText('@testchannel')).toBeInTheDocument();
            // 1000 becomes 1.0K due to formatCount
            expect(screen.getByText(/1.0K subscribers/)).toBeInTheDocument();
        });
    });

    it('handles delete channel action', async () => {
        (YouTubeService.getChannel as any).mockResolvedValue(createChannel());
        (YouTubeService.deleteChannel as any).mockResolvedValue(undefined);

        // Mock window.confirm
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/channel/ch1']}>
                    <Routes>
                        <Route path="/channel/:id" element={<ChannelPage />} />
                        <Route path="/" element={<div>Home Page</div>} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('Delete')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('Delete'));

        expect(confirmSpy).toHaveBeenCalled();
        await waitFor(() => {
            expect(YouTubeService.deleteChannel).toHaveBeenCalledWith('ch1');
            expect(screen.getByText('Home Page')).toBeInTheDocument();
        });
    });

    it('handles resync channel action', async () => {
        (YouTubeService.getChannel as any).mockResolvedValue(createChannel());
        (YouTubeService.resyncChannel as any).mockResolvedValue(undefined);

        // We don't mock location.reload here because ChannelPage just re-fetches data (calls setChannel)
        // Wait, looking at the code:
        // await YouTubeService.resyncChannel(id);
        // const data = await YouTubeService.getChannel(id);
        // setChannel(data);

        // So we should verify getChannel is called twice (initial + after resync)

        render(
            <AuthProvider>
                <MemoryRouter initialEntries={['/channel/ch1']}>
                    <Routes>
                        <Route path="/channel/:id" element={<ChannelPage />} />
                    </Routes>
                </MemoryRouter>
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByText('Resync')).toBeInTheDocument();
            expect(YouTubeService.getChannel).toHaveBeenCalledTimes(1);
        });

        fireEvent.click(screen.getByText('Resync'));

        await waitFor(() => {
            expect(YouTubeService.resyncChannel).toHaveBeenCalledWith('ch1');
            expect(YouTubeService.getChannel).toHaveBeenCalledTimes(2);
        });
    });
});
