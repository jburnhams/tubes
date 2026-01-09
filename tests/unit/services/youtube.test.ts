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

  describe('getVideos', () => {
    it('returns video list on successful fetch', async () => {
      const mockVideos = {
        videos: [
          { id: '1', title: 'Video 1' },
          { id: '2', title: 'Video 2' },
        ],
      };
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockVideos),
      });

      const result = await YouTubeService.getVideos();
      expect(result).toEqual(mockVideos);

      const expectedUrl = expect.stringMatching(/https:\/\/storage\.jonathanburnhams\.com\/api\/youtube\/videos\/random\?.*min_duration=300.*max_duration=3600/);

      expect(mockFetch).toHaveBeenCalledWith(
        expectedUrl,
        expect.objectContaining({
          method: 'GET',
          credentials: 'include',
        })
      );
    });

    it('throws error on failure', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      await expect(YouTubeService.getVideos()).rejects.toThrow(
        'Failed to fetch videos: 404'
      );
    });
  });

  describe('getVideo', () => {
    it('returns video details on successful fetch', async () => {
      const mockVideo = {
        youtube_id: '123',
        title: 'Video Details',
      };
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockVideo),
      });

      const result = await YouTubeService.getVideo('123');
      expect(result).toEqual(mockVideo);
      expect(mockFetch).toHaveBeenCalledWith(
        'https://storage.jonathanburnhams.com/api/youtube/video/123',
        expect.objectContaining({
          method: 'GET',
          credentials: 'include',
        })
      );
    });

    it('throws error on failure', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 403,
      });

      await expect(YouTubeService.getVideo('123')).rejects.toThrow(
        'Failed to fetch video details: 403'
      );
    });
  });
});
