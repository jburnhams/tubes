import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { Channel } from '../types/youtube';

export const ChannelsPage: React.FC = () => {
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
                setError('Failed to load channels. Please try again later.');
            } finally {
                setLoading(false);
            }
        };

        fetchChannels();
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[50vh]">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="text-center text-red-500 py-10">
                {error}
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto">
            <h1 className="text-2xl font-bold mb-6 text-gray-900">Channels</h1>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
                {channels.map((channel) => (
                    <Link
                        to={`/channel/${channel.youtube_id}`}
                        key={channel.youtube_id}
                        className="group relative flex flex-col items-center p-4 bg-white rounded-xl shadow-sm hover:shadow-md transition-all duration-200 border border-gray-100"
                    >
                        <div className="relative mb-3">
                            <img
                                src={channel.thumbnail_url || '/icons/channel-placeholder.png'}
                                className="h-24 w-24 rounded-full object-cover group-hover:scale-105 transition-transform duration-200"
                                alt={channel.title}
                                onError={(e) => { (e.target as HTMLImageElement).src = `https://ui-avatars.com/api/?name=${encodeURIComponent(channel.title)}` }}
                            />
                        </div>
                        <div className="text-center mb-1 w-full">
                            <h3 className="font-semibold text-gray-900 truncate px-2" title={channel.title}>
                                {channel.title}
                            </h3>
                        </div>

                        {/* Hover Description Overlay */}
                        <div className="absolute inset-0 bg-black/90 rounded-xl p-4 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10 pointer-events-none">
                            <p className="text-white text-xs text-center line-clamp-6">
                                {channel.description || "No description available."}
                            </p>
                        </div>
                    </Link>
                ))}
            </div>
            {channels.length === 0 && (
                <div className="text-center text-gray-500 py-10">
                    No channels found.
                </div>
            )}
        </div>
    );
};
