import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { YouTubeService } from '../../../src/services/youtube';

describe('YouTubeService', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should fetch channels correctly', async () => {
    const mockChannels = { channels: [{ youtube_id: '1', title: 'Test' }] };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => mockChannels,
    } as Response);

    const result = await YouTubeService.getChannels();

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/channels'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(mockChannels);
  });

  it('should fetch videos correctly', async () => {
    const mockVideos = { videos: [{ id: '1', title: 'Video' }] };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => mockVideos,
    } as Response);

    const result = await YouTubeService.getVideos();

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/videos/random'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(mockVideos);
  });

  it('should fetch single video correctly', async () => {
    const mockVideo = { youtube_id: '1', title: 'Video' };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => mockVideo,
    } as Response);

    const result = await YouTubeService.getVideo('1');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/video/1'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(result).toEqual(mockVideo);
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

  it('should delete channel correctly', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
    } as Response);

    await YouTubeService.deleteChannel('UC123');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/channel/UC123'),
      expect.objectContaining({
        method: 'DELETE',
        credentials: 'include',
      })
    );
  });

  it('should resync channel correctly', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
    } as Response);

    await YouTubeService.resyncChannel('UC123');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/channel/UC123/refresh'),
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      })
    );
  });

  it('should delete video correctly', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
    } as Response);

    await YouTubeService.deleteVideo('V123');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/video/V123'),
      expect.objectContaining({
        method: 'DELETE',
        credentials: 'include',
      })
    );
  });

  it('should resync video correctly', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
    } as Response);

    await YouTubeService.resyncVideo('V123');

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/video/V123/refresh'),
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      })
    );
  });
});
