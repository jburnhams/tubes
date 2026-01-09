import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { Video } from '../types/youtube';

const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
};

const formatViews = (views: number): string => {
    if (views >= 1000000) {
        return `${(views / 1000000).toFixed(1)}M views`;
    }
    if (views >= 1000) {
        return `${(views / 1000).toFixed(1)}K views`;
    }
    return `${views} views`;
};

const formatTimeAgo = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + " years ago";

    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + " months ago";

    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + " days ago";

    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + " hours ago";

    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + " minutes ago";

    return Math.floor(seconds) + " seconds ago";
};

interface VideoGridProps {
    channelId?: string;
}

export const VideoGrid: React.FC<VideoGridProps> = ({ channelId }) => {
    const [videos, setVideos] = useState<Video[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchVideos = async () => {
            try {
                const response = await YouTubeService.getVideos(channelId);
                setVideos(response.videos);
            } catch (err) {
                console.error('Failed to fetch videos:', err);
                setError('Failed to load videos. Please try again later.');
            } finally {
                setLoading(false);
            }
        };

        fetchVideos();
    }, [channelId]);

    if (loading) {
        return (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 gap-y-10">
                {[...Array(8)].map((_, i) => (
                    <div key={i} className="flex flex-col animate-pulse">
                        <div className="bg-gray-200 aspect-video rounded-xl mb-3"></div>
                        <div className="grid grid-cols-[36px_1fr] gap-3">
                            <div className="bg-gray-200 rounded-full w-9 h-9"></div>
                            <div className="flex flex-col gap-2">
                                <div className="bg-gray-200 h-4 rounded w-3/4"></div>
                                <div className="bg-gray-200 h-3 rounded w-1/2"></div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    if (error) {
        return <div className="text-center text-red-500 py-10">{error}</div>;
    }

    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 gap-y-10">
            {videos.map((video) => (
                <div key={video.id} className="flex flex-col cursor-pointer">
                    <div className="relative mb-3">
                        <Link to={`/video/${video.id}`} className="block relative">
                            <img className="w-full rounded-xl object-cover aspect-video hover:rounded-none transition-all duration-200" src={video.thumbnail} alt={video.title} />
                             <div className="absolute bottom-2 right-2 bg-black/80 text-white text-xs font-medium px-1.5 py-0.5 rounded">
                                {formatDuration(video.duration_seconds)}
                            </div>
                        </Link>
                    </div>
                    <div className="grid grid-cols-[36px_1fr] gap-3">
                        <div className="relative group">
                            <a href={`https://www.youtube.com/channel/${video.channel_id}`} target="_blank" rel="noopener noreferrer">
                                <img className="rounded-full w-9 h-9 object-cover" src={video.channel_thumbnail} alt={video.channel_title} />
                            </a>
                            {/* Tooltip - Simplified as we don't have subscriber count */}
                            <div className="absolute top-10 left-0 bg-white border border-gray-200 shadow-lg rounded-lg p-3 w-48 z-50 hidden group-hover:flex items-center gap-3">
                                <img className="w-10 h-10 rounded-full" src={video.channel_thumbnail} alt={video.channel_title} />
                                <div>
                                    <p className="font-bold text-sm text-gray-900 line-clamp-1">{video.channel_title}</p>
                                </div>
                            </div>
                        </div>
                        <div className="flex flex-col">
                            <Link to={`/video/${video.id}`} className="text-sm font-bold text-gray-900 leading-5 mb-1 line-clamp-2 hover:text-blue-600" title={video.title}>
                                {video.title}
                            </Link>
                            <a href={`https://www.youtube.com/channel/${video.channel_id}`} target="_blank" rel="noopener noreferrer" className="text-xs text-gray-600 hover:text-gray-900 transition-colors">
                                {video.channel_title}
                            </a>
                            <div className="text-xs text-gray-600">
                                {formatViews(video.view_count)} &#183; {formatTimeAgo(video.published_at)}
                            </div>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
};
