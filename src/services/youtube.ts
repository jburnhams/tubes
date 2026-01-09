import { ChannelListResponse, VideoListResponse, VideoDetail } from '../types/youtube';

const CHANNELS_API_URL = 'https://storage.jonathanburnhams.com/api/youtube/channels';
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

  static async getVideos(): Promise<VideoListResponse> {
    const response = await fetch(VIDEOS_API_URL, {
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
}
