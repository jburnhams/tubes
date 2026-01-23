import { ChannelListResponse, VideoListResponse, VideoDetail, ChannelDetail } from '../types/youtube';

const CHANNELS_API_URL = 'https://storage.jonathanburnhams.com/api/youtube/channels';
const CHANNEL_DETAIL_API_URL_BASE = 'https://storage.jonathanburnhams.com/api/youtube/channel';
const VIDEOS_API_URL = 'https://storage.jonathanburnhams.com/api/youtube/videos/random';
const VIDEO_DETAIL_API_URL_BASE = 'https://storage.jonathanburnhams.com/api/youtube/video';

export class YouTubeService {
  static async getChannels(): Promise<ChannelListResponse> {
    const response = await fetch(CHANNELS_API_URL, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch channels: ${response.status}`);
    }

    return response.json();
  }

  static async getVideos(channelId?: string): Promise<VideoListResponse> {
    const url = new URL(VIDEOS_API_URL);
    url.searchParams.append('min_duration', '300');
    url.searchParams.append('max_duration', '3600');
    if (channelId) {
      url.searchParams.append('channel_id', channelId);
    }

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch videos: ${response.status}`);
    }

    return response.json();
  }

  static async getVideo(id: string): Promise<VideoDetail> {
    const response = await fetch(`${VIDEO_DETAIL_API_URL_BASE}/${id}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch video details: ${response.status}`);
    }

    return response.json();
  }

  static async getChannel(id: string): Promise<ChannelDetail> {
    const response = await fetch(`${CHANNEL_DETAIL_API_URL_BASE}/${id}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch channel details: ${response.status}`);
    }

    const data = await response.json();

    // Robustness: Check if we have the expected stats, if not, try to parse from raw_json
    if ((data.view_count === null || data.view_count === undefined) && data.raw_json) {
      try {
        const raw = JSON.parse(data.raw_json);
        if (raw.statistics) {
          data.view_count = raw.statistics.viewCount ? parseInt(raw.statistics.viewCount, 10) : null;
          data.subscriber_count = raw.statistics.subscriberCount ? parseInt(raw.statistics.subscriberCount, 10) : null;
          data.video_count = raw.statistics.videoCount ? parseInt(raw.statistics.videoCount, 10) : null;
        }
      } catch (e) {
        console.warn('Failed to parse raw_json for channel fallback stats', e);
      }
    }

    return data;
  }

  static async searchVideos(query: string, limit: number = 20): Promise<VideoListResponse> {
    const url = new URL('https://storage.jonathanburnhams.com/api/youtube/videos');
    url.searchParams.append('title_contains', query);
    url.searchParams.append('sort_by', 'published_at');
    url.searchParams.append('sort_order', 'desc');
    url.searchParams.append('limit', limit.toString());
    url.searchParams.append('offset', '0');

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to search videos: ${response.status}`);
    }

    return response.json();
  }
}
