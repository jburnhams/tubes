import React from 'react';
import { Channel } from '../types/youtube';

interface ChannelCardProps {
  channel: Channel;
  onClick: (channel: Channel) => void;
}

export const ChannelCard: React.FC<ChannelCardProps> = ({ channel, onClick }) => {
  return (
    <div
      className="bg-white rounded-lg shadow-md hover:shadow-xl transition-shadow cursor-pointer overflow-hidden flex flex-col h-full"
      onClick={() => onClick(channel)}
      data-testid="channel-card"
    >
      <div className="aspect-square w-full overflow-hidden bg-gray-100">
        <img
          src={channel.thumbnail_url}
          alt={channel.title}
          className="w-full h-full object-cover"
          loading="lazy"
        />
      </div>
      <div className="p-4 flex-1 flex items-center justify-center text-center">
        <h3 className="font-semibold text-gray-800 text-lg line-clamp-2">{channel.title}</h3>
      </div>
    </div>
  );
};
