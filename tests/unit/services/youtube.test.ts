import { YouTubeService } from '@/src/services/youtube';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('YouTubeService', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    global.fetch = mockFetch;
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getChannels', () => {
    it('returns channel list on successful fetch', async () => {
      const mockChannels = {
        channels: [
          { youtube_id: '1', title: 'Channel 1', thumbnail_url: 'url1' },
          { youtube_id: '2', title: 'Channel 2', thumbnail_url: 'url2' },
        ],
      };
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockChannels),
      });

      const result = await YouTubeService.getChannels();
      expect(result).toEqual(mockChannels);
      expect(mockFetch).toHaveBeenCalledWith(
        'https://storage.jonathanburnhams.com/api/youtube/channels',
        expect.objectContaining({
          method: 'GET',
          credentials: 'include',
        })
      );
    });

    it('throws error on failure', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });

      await expect(YouTubeService.getChannels()).rejects.toThrow(
        'Failed to fetch channels: 500'
      );
    });
  });
});
