export interface Channel {
  youtube_id: string;
  title: string;
  description: string;
  custom_url: string;
  thumbnail_url: string;
  best_thumbnail_url: string | null;
  published_at: string;
  country: string | null;
}

export interface ChannelListResponse {
  channels: Channel[];
}

export interface Video {
  id: string;
  title: string;
  description: string;
  thumbnail: string;
  duration_seconds: number;
  channel_id: string;
  channel_title: string;
  channel_thumbnail: string;
  published_at: string;
  view_count: number;
}

export interface VideoListResponse {
  videos: Video[];
}
