import { ChannelListResponse, VideoListResponse } from '../types/youtube';

const CHANNELS_API_URL = 'https://storage.jonathanburnhams.com/api/youtube/channels';
const VIDEOS_API_URL = 'https://storage.jonathanburnhams.com/api/youtube/videos/random';

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
}
