import { ChannelListResponse, VideoListResponse, VideoDetail, ChannelDetail } from '../types/youtube';
import { ConfigService } from './config';

// Default to empty string to allow Vite proxy to handle requests to vps.jonathanburnhams.com
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const CHANNELS_API_URL = `${API_BASE_URL}/api/youtube/channels`;
const CHANNEL_DETAIL_API_URL_BASE = `${API_BASE_URL}/api/youtube/channel`;
const VIDEOS_API_URL = `${API_BASE_URL}/api/youtube/videos/random`;
const VIDEO_DETAIL_API_URL_BASE = `${API_BASE_URL}/api/youtube/video`;

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
    // Construct URL handling both relative (proxy) and absolute (env var) paths
    const baseUrl = VIDEOS_API_URL.startsWith('http') ? VIDEOS_API_URL : new URL(VIDEOS_API_URL, window.location.origin).toString();
    const url = new URL(baseUrl);
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
