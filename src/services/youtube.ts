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

    return response.json();
  }

  static async deleteChannel(id: string): Promise<void> {
    const response = await fetch(`${CHANNEL_DETAIL_API_URL_BASE}/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete channel: ${response.status}`);
    }
  }

  static async resyncChannel(id: string): Promise<void> {
    const response = await fetch(`${CHANNEL_DETAIL_API_URL_BASE}/${id}/refresh`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to resync channel: ${response.status}`);
    }
  }

  static async deleteVideo(id: string): Promise<void> {
    const response = await fetch(`${VIDEO_DETAIL_API_URL_BASE}/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete video: ${response.status}`);
    }
  }

  static async resyncVideo(id: string): Promise<void> {
    const response = await fetch(`${VIDEO_DETAIL_API_URL_BASE}/${id}/refresh`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to resync video: ${response.status}`);
    }
  }
}
