import React from 'react';
import { Channel } from '../types/youtube';

interface ChannelModalProps {
  channel: Channel | null;
  onClose: () => void;
}

export const ChannelModal: React.FC<ChannelModalProps> = ({ channel, onClose }) => {
  if (!channel) return null;

  // Use best_thumbnail_url if available, otherwise fall back to thumbnail_url
  const bigImageUrl = channel.best_thumbnail_url || channel.thumbnail_url;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
      data-testid="channel-modal-backdrop"
    >
      <div
        className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto flex flex-col md:flex-row"
        onClick={(e) => e.stopPropagation()}
        data-testid="channel-modal-content"
      >
        <div className="md:w-1/2 bg-gray-100 flex items-center justify-center p-4">
          <img
            src={bigImageUrl}
            alt={channel.title}
            className="w-full h-auto rounded-lg shadow-sm"
          />
        </div>
        <div className="md:w-1/2 p-6 md:p-8 flex flex-col">
          <div className="flex justify-between items-start mb-4">
            <h2 className="text-2xl font-bold text-gray-900">{channel.title}</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 focus:outline-none"
              aria-label="Close modal"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="flex-1 space-y-4">
            <p className="text-sm text-gray-500 font-medium">{channel.custom_url}</p>

            {channel.country && (
              <div className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                {channel.country}
              </div>
            )}

            <p className="text-gray-700 whitespace-pre-wrap">{channel.description}</p>

            <div className="text-xs text-gray-400 mt-4 pt-4 border-t border-gray-100">
              Published: {new Date(channel.published_at).toLocaleDateString()}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
