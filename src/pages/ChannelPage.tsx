import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { ChannelDetail } from '../types/youtube';
import { VideoGrid } from '../components/VideoGrid';

function formatCount(count: number): string {
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
  const navigate = useNavigate();
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
          {/* Since we don't have a dedicated banner URL in the current API response (it's inside raw_json maybe, but complicated),
              we'll use a placeholder or best_thumbnail_url blurred if we wanted, but for now just a color or placeholder.
              Actually, the user said "show the big thumbnail image".
              Usually channel pages have a banner.
              If the user meant the profile picture is the "big thumbnail", we show it below.
              If they meant the banner, I don't have it easily.
              I will assume "big thumbnail image" refers to the channel avatar which can be high res (best_thumbnail_url).
              I'll put a default banner.
           */}
           <div className="w-full h-full bg-gradient-to-r from-blue-500 to-purple-600"></div>
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
            <div className="flex flex-wrap gap-2 justify-center md:justify-start">
              <button className="bg-black text-white px-6 py-2 rounded-full font-medium hover:bg-gray-800 transition-colors">
                  Subscribe
              </button>
              <button
                onClick={async () => {
                  if (!id) return;
                  if (confirm('Are you sure you want to delete this channel and all its videos?')) {
                    try {
                      await YouTubeService.deleteChannel(id);
                      navigate('/');
                    } catch (err) {
                      console.error('Failed to delete channel', err);
                      alert('Failed to delete channel');
                    }
                  }
                }}
                className="bg-red-600 text-white px-6 py-2 rounded-full font-medium hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
              <button
                onClick={async () => {
                  if (!id) return;
                  try {
                    setLoading(true);
                    await YouTubeService.resyncChannel(id);
                    const data = await YouTubeService.getChannel(id);
                    setChannel(data);
                  } catch (err) {
                    console.error('Failed to resync channel', err);
                    alert('Failed to resync channel');
                    setLoading(false);
                  }
                  // We don't need finally { setLoading(false) } because the success path does it via re-render or we should ensure it does.
                  // Actually, fetchChannel in useEffect also manages loading.
                  // If we manually setChannel(data), we must ensure loading is false.
                  setLoading(false);
                }}
                className="bg-blue-600 text-white px-6 py-2 rounded-full font-medium hover:bg-blue-700 transition-colors"
              >
                Resync
              </button>
            </div>
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
