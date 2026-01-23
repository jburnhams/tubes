import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { Video } from '../types/youtube';
import { VideoGrid } from '../components/VideoGrid';

export const SearchResultsPage: React.FC = () => {
    const [searchParams] = useSearchParams();
    const query = searchParams.get('q') || '';

    const [videos, setVideos] = useState<Video[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const performSearch = async () => {
            if (!query.trim()) {
                setVideos([]);
                setLoading(false);
                return;
            }

            try {
                setLoading(true);
                setError(null);
                const response = await YouTubeService.searchVideos(query);
                setVideos(response.videos);
            } catch (err) {
                console.error('Failed to search videos:', err);
                setError('Failed to search videos. Please try again later.');
            } finally {
                setLoading(false);
            }
        };

        performSearch();
    }, [query]);

    if (!query.trim()) {
        return (
            <div className="text-center text-gray-500 py-10">
                Enter a search query to find videos.
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex justify-center items-center min-h-[50vh]">
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
        <div>
            <h1 className="text-xl font-semibold mb-4 text-gray-900">
                Search results for "{query}"
            </h1>
            {videos.length === 0 ? (
                <div className="text-center text-gray-500 py-10">
                    No videos found for "{query}". Try a different search term.
                </div>
            ) : (
                <VideoGrid videos={videos} />
            )}
        </div>
    );
};
