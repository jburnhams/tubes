import { describe, it, expect, vi, beforeEach } from 'vitest';
import { YouTubeService } from '../../../src/services/youtube';

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('YouTubeService', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  describe('getChannel', () => {
    it('should return complete data when API response is complete', async () => {
      const mockResponse = {
        youtube_id: '123',
        title: 'Test Channel',
        view_count: 1000,
        subscriber_count: 500,
        video_count: 10,
        raw_json: '{}'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const result = await YouTubeService.getChannel('123');
      expect(result.view_count).toBe(1000);
      expect(result.subscriber_count).toBe(500);
    });

    it('should fallback to raw_json when top-level stats are missing', async () => {
      const rawJson = JSON.stringify({
        statistics: {
          viewCount: "2000",
          subscriberCount: "600",
          videoCount: "20"
        }
      });

      const mockResponse = {
        youtube_id: '123',
        title: 'Test Channel',
        view_count: null,
        subscriber_count: null,
        video_count: null,
        raw_json: rawJson
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const result = await YouTubeService.getChannel('123');
      expect(result.view_count).toBe(2000);
      expect(result.subscriber_count).toBe(600);
      expect(result.video_count).toBe(20);
    });

    it('should handle missing raw_json gracefully', async () => {
      const mockResponse = {
        youtube_id: '123',
        title: 'Test Channel',
        view_count: null,
        subscriber_count: null,
        video_count: null,
        raw_json: ""
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const result = await YouTubeService.getChannel('123');
      expect(result.view_count).toBeNull();
    });

    it('should handle malformed raw_json gracefully', async () => {
      const mockResponse = {
        youtube_id: '123',
        title: 'Test Channel',
        view_count: null,
        subscriber_count: null,
        video_count: null,
        raw_json: "{invalid_json}"
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => { });

      const result = await YouTubeService.getChannel('123');
      expect(result.view_count).toBeNull();

      consoleSpy.mockRestore();
    });
  });
});
