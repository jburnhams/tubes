import { ChannelListResponse, VideoListResponse, VideoDetail, ChannelDetail } from '../types/youtube';
import { ConfigService } from './config';

const CHANNELS_API_URL = '/api/youtube/channels';
const CHANNEL_DETAIL_API_URL_BASE = '/api/youtube/channel';
const VIDEOS_API_URL = '/api/youtube/videos/random';
const VIDEO_DETAIL_API_URL_BASE = '/api/youtube/video';

const getHeaders = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const cookie = ConfigService.getCookie();
  if (cookie) {
    headers['h-Cookie'] = cookie;
  }
  return headers;
};

export class YouTubeService {
  static async getChannels(): Promise<ChannelListResponse> {
    const response = await fetch(CHANNELS_API_URL, {
      method: 'GET',
      headers: getHeaders(),
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch channels: ${response.status}`);
    }

    return response.json();
  }

  static async getVideos(channelId?: string): Promise<VideoListResponse> {
    const url = new URL(VIDEOS_API_URL, window.location.origin);
    url.searchParams.append('min_duration', '300');
    url.searchParams.append('max_duration', '3600');
    if (channelId) {
      url.searchParams.append('channel_id', channelId);
    }

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: getHeaders(),
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
      headers: getHeaders(),
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
      headers: getHeaders(),
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch channel details: ${response.status}`);
    }

    return response.json();
  }
}
