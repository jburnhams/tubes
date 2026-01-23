import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { Channel } from '../types/youtube';

export const Sidebar: React.FC = () => {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);


  useEffect(() => {
    const fetchChannels = async () => {
      try {
        setLoading(true);
        const data = await YouTubeService.getChannels();
        setChannels(data.channels);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch channels', err);
        setError('Failed to load channels.');
      } finally {
        setLoading(false);
      }
    };

    fetchChannels();
  }, []);



  return (
    <nav className="fixed left-0 bottom-0 top-14 bg-white z-[200] pt-1 w-[72px] md:w-52 border-r border-gray-200 overflow-y-auto pb-10">
      <div className="flex flex-col">
        <Link to="/" className="flex flex-col md:flex-row items-center md:items-start px-0 md:px-6 py-2 md:py-3 cursor-pointer hover:bg-gray-100 justify-center md:justify-start">
          <img src="/icons/home.svg" className="h-6 mb-1 md:mb-0 md:mr-4" alt="Home" />
          <div className="text-[10px] md:text-sm text-gray-700">Home</div>
        </Link>
        <Link to="/channels" className="flex flex-col md:flex-row items-center md:items-start px-0 md:px-6 py-2 md:py-3 cursor-pointer hover:bg-gray-100 justify-center md:justify-start">
          <img src="/icons/explore.svg" className="h-6 mb-1 md:mb-0 md:mr-4" alt="Explore" />
          <div className="text-[10px] md:text-sm text-gray-700">Explore</div>
        </Link>

        {/* Subscriptions Toggle Header */}
        {/* Subscriptions Header */}
        <div
          className="flex flex-col md:flex-row items-center md:items-start px-0 md:px-6 py-2 md:py-3 cursor-pointer hover:bg-gray-100 justify-center md:justify-start group"
        >
          <img src="/icons/subscriptions.svg" className="h-6 mb-1 md:mb-0 md:mr-4" alt="Subscriptions" />
          <div className="text-[10px] md:text-sm flex-1 text-left">Subscriptions</div>
        </div>

        {/* Subscriptions List (Desktop Only) */}
        <div className="hidden md:block">
          <div className="mt-0 mb-2">
            {error && (
              <div className="px-6 py-2 text-xs text-red-500">{error}</div>
            )}
            {!error && channels.map((channel) => (
              <Link to={`/channel/${channel.youtube_id}`} key={channel.youtube_id} className="flex items-center pl-14 pr-6 py-2 cursor-pointer hover:bg-gray-100" title={channel.title}>
                <img
                  src={channel.thumbnail_url || '/icons/channel-placeholder.png'}
                  className="h-6 w-6 rounded-full mr-3 object-cover"
                  alt={channel.title}
                  onError={(e) => { (e.target as HTMLImageElement).src = `https://ui-avatars.com/api/?name=${encodeURIComponent(channel.title)}` }}
                />
                <div className="text-sm text-gray-700 truncate">{channel.title}</div>
              </Link>
            ))}
            {!error && channels.length === 0 && !loading && (
              <div className="px-6 py-2 text-xs text-gray-500">No channels found</div>
            )}
          </div>
        </div>

        <Link to="/channels" className="flex flex-col md:flex-row items-center md:items-start px-0 md:px-6 py-2 md:py-3 cursor-pointer hover:bg-gray-100 justify-center md:justify-start">
          <img src="/icons/originals.svg" className="h-6 mb-1 md:mb-0 md:mr-4" alt="Originals" />
          <div className="text-[10px] md:text-sm text-gray-700">Originals</div>
        </Link>
        <Link to="/channels" className="flex flex-col md:flex-row items-center md:items-start px-0 md:px-6 py-2 md:py-3 cursor-pointer hover:bg-gray-100 justify-center md:justify-start">
          <img src="/icons/youtube-music.svg" className="h-6 mb-1 md:mb-0 md:mr-4" alt="YouTube Music" />
          <div className="text-[10px] md:text-sm whitespace-nowrap overflow-hidden text-ellipsis text-gray-700">Music</div>
        </Link>
        <Link to="/channels" className="flex flex-col md:flex-row items-center md:items-start px-0 md:px-6 py-2 md:py-3 cursor-pointer hover:bg-gray-100 justify-center md:justify-start">
          <img src="/icons/library.svg" className="h-6 mb-1 md:mb-0 md:mr-4" alt="Library" />
          <div className="text-[10px] md:text-sm text-gray-700">Library</div>
        </Link>

        {/* Separator for desktop */}
        <div className="hidden md:block border-t border-gray-200 my-2 mx-0"></div>
      </div>
    </nav>
  );
};
