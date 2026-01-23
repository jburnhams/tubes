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

export interface ChannelDetail extends Channel {
  view_count: number | null;
  subscriber_count: number | null;
  video_count: number | null;
  upload_playlist_id: string;
  best_thumbnail_width: number | null;
  best_thumbnail_height: number | null;
  raw_json: string;
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

export interface VideoDetail {
  youtube_id: string;
  title: string;
  description: string;
  published_at: string;
  channel_id: string;
  thumbnail_url: string;
  duration: string;
  raw_json: string;
  created_at: string;
  updated_at: string;
  duration_seconds: number;
  view_count: number;
  like_count: number;
  comment_count: number;
  best_thumbnail_url: string;
  best_thumbnail_width: number;
  best_thumbnail_height: number;
  definition: string;
  dimension: string;
  licensed_content: number;
  caption: number;
  privacy_status: string;
  embeddable: number;
  made_for_kids: number;
}
