import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { YouTubeService } from '../../../src/services/youtube';

describe('YouTubeService', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should fetch channel details correctly', async () => {
    const mockChannel = {
      youtube_id: 'UC123',
      title: 'Test Channel',
      description: 'Test Description',
      subscriber_count: 1000,
      video_count: 50,
      view_count: 5000,
      best_thumbnail_url: 'http://example.com/thumb.jpg',
    };

    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => mockChannel,
    } as Response);

    const channel = await YouTubeService.getChannel('UC123');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/youtube/channel/UC123'),
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
      })
    );
    expect(channel).toEqual(mockChannel);
  });

  it('should throw an error when fetching channel fails', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
    } as Response);

    await expect(YouTubeService.getChannel('UC123')).rejects.toThrow('Failed to fetch channel details: 404');
  });
});
