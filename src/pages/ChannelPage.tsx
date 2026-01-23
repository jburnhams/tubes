import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { ChannelDetail } from '../types/youtube';
import { VideoGrid } from '../components/VideoGrid';

function formatCount(count: number | null | undefined): string {
  if (count === null || count === undefined) {
    return 'N/A';
  }
  if (count >= 1000000) {
    return (count / 1000000).toFixed(1) + 'M';
  }
  if (count >= 1000) {
    return (count / 1000).toFixed(1) + 'K';
  }
  return count.toString();
}

export const ChannelPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [channel, setChannel] = useState<ChannelDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchChannel = async () => {
      if (!id) return;
      try {
        setLoading(true);
        const data = await YouTubeService.getChannel(id);
        setChannel(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch channel', err);
        setError('Failed to load channel details.');
      } finally {
        setLoading(false);
      }
    };

    fetchChannel();
  }, [id]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full pt-10">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error || !channel) {
    return (
      <div className="text-center text-red-600 p-4 pt-10">
        {error || 'Channel not found'}
      </div>
    );
  }

  return (
    <div className="max-w-[1700px] mx-auto px-4 pt-6">
      {/* Banner / Header */}
      <div className="w-full h-32 md:h-48 lg:h-64 bg-gray-200 rounded-xl overflow-hidden mb-6 relative">
        <img
          src={channel.best_thumbnail_url || channel.thumbnail_url}
          alt={`${channel.title} banner`}
          className="w-full h-full object-cover object-center"
        />
      </div>

      {/* Channel Header Info */}
      <div className="flex flex-col md:flex-row items-center md:items-start gap-6 mb-8 px-4 md:px-12">
        {/* Avatar */}
        <div className="flex-shrink-0">
          <img
            src={channel.best_thumbnail_url || channel.thumbnail_url}
            alt={channel.title}
            className="w-32 h-32 md:w-40 md:h-40 rounded-full border-4 border-white shadow-lg object-cover"
          />
        </div>

        {/* Metadata */}
        <div className="flex flex-col items-center md:items-start text-center md:text-left pt-2 flex-1">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">{channel.title}</h1>
          <div className="text-gray-600 flex flex-wrap justify-center md:justify-start gap-x-4 gap-y-1 mb-3 text-sm md:text-base">
            <span className="font-semibold">{channel.custom_url}</span>
            <span>{formatCount(channel.subscriber_count)} subscribers</span>
            <span>{formatCount(channel.video_count)} videos</span>
            <span>{formatCount(channel.view_count)} views</span>
          </div>
          <p className="text-gray-500 text-sm max-w-2xl line-clamp-2 md:line-clamp-3 mb-4">
            {channel.description}
          </p>
          <button className="bg-black text-white px-6 py-2 rounded-full font-medium hover:bg-gray-800 transition-colors">
            Subscribe
          </button>
        </div>
      </div>

      {/* Tabs (Placeholder) */}
      <div className="border-b border-gray-200 mb-6">
        <div className="flex gap-8 px-4 md:px-12 text-sm font-medium text-gray-600 overflow-x-auto">
          <button className="pb-3 border-b-2 border-black text-black">Home</button>
          <button className="pb-3 hover:text-black transition-colors">Videos</button>
          <button className="pb-3 hover:text-black transition-colors">Shorts</button>
          <button className="pb-3 hover:text-black transition-colors">Playlists</button>
          <button className="pb-3 hover:text-black transition-colors">Community</button>
        </div>
      </div>

      {/* Content Area */}
      <div className="px-4 md:px-12 pb-10">
        <VideoGrid channelId={id} />
      </div>
    </div>
  );
};
