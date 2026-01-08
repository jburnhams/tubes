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
