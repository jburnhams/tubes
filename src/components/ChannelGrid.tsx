import React, { useEffect, useState } from 'react';
import { YouTubeService } from '../services/youtube';
import { Channel } from '../types/youtube';
import { ChannelCard } from './ChannelCard';
import { ChannelModal } from './ChannelModal';

export const ChannelGrid: React.FC = () => {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null);

  useEffect(() => {
    const fetchChannels = async () => {
      try {
        setLoading(true);
        const data = await YouTubeService.getChannels();
        setChannels(data.channels);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch channels', err);
        setError('Failed to load channels. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchChannels();
  }, []);

  const handleChannelClick = (channel: Channel) => {
    setSelectedChannel(channel);
  };

  const handleCloseModal = () => {
    setSelectedChannel(null);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border-l-4 border-red-500 p-4 my-8 mx-auto max-w-2xl">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
        {channels.map((channel) => (
          <ChannelCard
            key={channel.youtube_id}
            channel={channel}
            onClick={handleChannelClick}
          />
        ))}
      </div>

      {selectedChannel && (
        <ChannelModal
          channel={selectedChannel}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
};
