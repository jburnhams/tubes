import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { VideoDetail } from '../types/youtube';

export const VideoPage = () => {
  const { id } = useParams<{ id: string }>();
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchVideo = async () => {
      if (!id) return;

      try {
        setLoading(true);
        const data = await YouTubeService.getVideo(id);
        setVideo(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch video', err);
        setError('Failed to load video details.');
      } finally {
        setLoading(false);
      }
    };

    fetchVideo();
  }, [id]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error || !video) {
    return (
      <div className="text-center text-red-600 p-4">
        {error || 'Video not found'}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 max-w-6xl mx-auto">
      {/* Video Player Placeholder / Thumbnail */}
      <div className="w-full aspect-video bg-black rounded-xl overflow-hidden shadow-lg">
        <img
          src={video.best_thumbnail_url || video.thumbnail_url}
          alt={video.title}
          className="w-full h-full object-contain"
        />
      </div>

      {/* Video Metadata */}
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold text-gray-900">{video.title}</h1>

        <div className="flex justify-between items-center text-sm text-gray-600 border-b pb-4">
          <div className="flex gap-4">
            <span>{video.view_count.toLocaleString()} views</span>
            <span>{new Date(video.published_at).toLocaleDateString()}</span>
          </div>
          <div className="flex gap-4">
             <span className="flex items-center gap-1">
               👍 {video.like_count.toLocaleString()}
             </span>
          </div>
        </div>

        <div className="bg-gray-100 p-4 rounded-xl mt-2 whitespace-pre-wrap text-sm text-gray-800">
          {video.description}
        </div>
      </div>
    </div>
  );
};
