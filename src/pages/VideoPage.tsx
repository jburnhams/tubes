import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { YouTubeService } from '../services/youtube';
import { VideoDetail, Video, Channel } from '../types/youtube';
import { TubePlayerWrapper } from '../components/TubePlayerWrapper';
import { useAuth } from '../context/AuthContext';

function formatCount(count: number): string {
  if (count >= 1000000) {
    return (count / 1000000).toFixed(1) + 'M';
  }
  if (count >= 1000) {
    return (count / 1000).toFixed(1) + 'K';
  }
  return count.toString();
}

function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  let interval = seconds / 31536000;
  if (interval > 1) {
    return Math.floor(interval) + ' years ago';
  }
  interval = seconds / 2592000;
  if (interval > 1) {
    return Math.floor(interval) + ' months ago';
  }
  interval = seconds / 86400;
  if (interval > 1) {
    return Math.floor(interval) + ' days ago';
  }
  interval = seconds / 3600;
  if (interval > 1) {
    return Math.floor(interval) + ' hours ago';
  }
  interval = seconds / 60;
  if (interval > 1) {
    return Math.floor(interval) + ' minutes ago';
  }
  return Math.floor(seconds) + ' seconds ago';
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export const VideoPage = () => {
  const { id } = useParams<{ id: string }>();
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [recommendations, setRecommendations] = useState<Video[]>([]);
  const [channel, setChannel] = useState<Channel | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);

  useEffect(() => {
    const fetchVideoData = async () => {
      if (!id) return;

      try {
        setLoading(true);
        setError(null);

        // Fetch main video details
        const videoData = await YouTubeService.getVideo(id);
        setVideo(videoData);

        // Fetch recommendations (random videos)
        const recData = await YouTubeService.getVideos();
        setRecommendations(recData.videos);

        // Fetch channels to find the current video's channel info
        const channelsData = await YouTubeService.getChannels();
        const currentChannel = channelsData.channels.find(c => c.youtube_id === videoData.channel_id);
        setChannel(currentChannel || null);

      } catch (err) {
        console.error('Failed to fetch video data', err);
        setError('Failed to load video details.');
      } finally {
        setLoading(false);
      }
    };

    fetchVideoData();
  }, [id]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full pt-10">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error || !video) {
    return (
      <div className="text-center text-red-600 p-4 pt-10">
        {error || 'Video not found'}
      </div>
    );
  }

  return (
    <div className="flex flex-col xl:flex-row gap-6 max-w-[1700px] mx-auto px-4 pt-6">
      {/* Main Content Column */}
      <div className="flex-1 overflow-hidden">
        {/* Video Player */}
        <div className="w-full aspect-video bg-black rounded-xl overflow-hidden shadow-lg mb-4">
          <TubePlayerWrapper videoId={id || ''} sessionId={user?.session_id} />
        </div>

        {/* Title */}
        <h1 className="text-xl font-bold text-gray-900 mb-2 line-clamp-2">{video.title}</h1>

        {/* Top Row: Channel Info & Actions */}
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <Link to={channel ? `/channel/${channel.youtube_id}` : '#'} className="w-10 h-10 rounded-full bg-gray-200 overflow-hidden flex-shrink-0">
               {channel ? (
                 <img src={channel.thumbnail_url} alt={channel.title} className="w-full h-full object-cover" />
               ) : (
                 <div className="w-full h-full flex items-center justify-center text-gray-500 text-xs">?</div>
               )}
            </Link>
            <div className="flex flex-col">
               <Link to={channel ? `/channel/${channel.youtube_id}` : '#'} className="font-bold text-gray-900 text-sm hover:text-gray-700">{channel?.title || 'Unknown Channel'}</Link>
               <span className="text-xs text-gray-500">1.2M subscribers</span>
            </div>
            <button className="bg-black text-white px-4 py-2 rounded-full text-sm font-medium hover:bg-gray-800 ml-4 transition-colors">
              Subscribe
            </button>
          </div>

          <div className="flex items-center gap-2 overflow-x-auto pb-2 sm:pb-0 scrollbar-hide">
            <div className="flex bg-gray-100 rounded-full overflow-hidden h-9 items-center">
               <button className="px-4 h-full hover:bg-gray-200 flex items-center gap-2 border-r border-gray-300 text-sm font-medium transition-colors">
                 <span className="text-lg">👍</span> {formatCount(video.like_count)}
               </button>
               <button className="px-4 h-full hover:bg-gray-200 text-sm transition-colors">👎</button>
            </div>
            <button className="bg-gray-100 px-4 h-9 rounded-full hover:bg-gray-200 flex items-center gap-2 text-sm font-medium transition-colors">
               Share
            </button>
            <button className="bg-gray-100 px-4 h-9 rounded-full hover:bg-gray-200 flex items-center gap-2 text-sm font-medium transition-colors">
               Download
            </button>
            <button className="bg-gray-100 w-9 h-9 rounded-full hover:bg-gray-200 flex items-center justify-center transition-colors">
               ...
            </button>
          </div>
        </div>

        {/* Description Box */}
        <div
          className={`bg-gray-100 rounded-xl p-3 text-sm cursor-pointer hover:bg-gray-200 transition-colors ${isDescriptionExpanded ? '' : 'overflow-hidden'}`}
          onClick={() => setIsDescriptionExpanded(!isDescriptionExpanded)}
        >
          <div className="font-bold mb-2 text-gray-800">
             {formatCount(video.view_count)} views • {timeAgo(video.published_at)}
          </div>
          <div className={`whitespace-pre-wrap text-gray-800 ${isDescriptionExpanded ? '' : 'line-clamp-2'}`}>
             {video.description}
          </div>
          {!isDescriptionExpanded && (
            <div className="mt-1 font-bold text-gray-600">Show more</div>
          )}
           {isDescriptionExpanded && (
            <div className="mt-1 font-bold text-gray-600">Show less</div>
          )}
        </div>

        {/* Comments Section (Placeholder) */}
        <div className="mt-6 hidden md:block">
           <h3 className="text-xl font-bold mb-6">{video.comment_count} Comments</h3>
           <div className="flex gap-4 mb-6">
              <div className="w-10 h-10 rounded-full bg-purple-600 text-white flex items-center justify-center font-bold text-sm">
                 {user?.name?.[0]?.toUpperCase() || 'U'}
              </div>
              <div className="flex-1">
                 <input
                   type="text"
                   placeholder="Add a comment..."
                   className="w-full border-b border-gray-300 focus:border-black outline-none py-1 bg-transparent transition-colors"
                 />
              </div>
           </div>
        </div>
      </div>

      {/* Recommendations Column */}
      <div className="w-full xl:w-[400px] flex flex-col gap-3 pb-10">
         {recommendations.filter(r => r.id !== video.youtube_id).map(rec => (
            <Link to={`/video/${rec.id}`} key={rec.id} className="flex gap-2 group">
               <div className="relative w-40 flex-shrink-0 aspect-video rounded-lg overflow-hidden bg-gray-200">
                   <img src={rec.thumbnail} alt={rec.title} className="w-full h-full object-cover" />
                   <span className="absolute bottom-1 right-1 bg-black/80 text-white text-xs px-1 rounded font-medium">
                       {formatDuration(rec.duration_seconds)}
                   </span>
               </div>
               <div className="flex flex-col gap-1 min-w-0">
                   <div className="font-bold text-sm line-clamp-2 leading-tight text-gray-900 group-hover:text-indigo-600 transition-colors">
                       {rec.title}
                   </div>
                   <div className="text-xs text-gray-500 hover:text-gray-700 transition-colors">{rec.channel_title}</div>
                   <div className="text-xs text-gray-500">
                       {formatCount(rec.view_count)} views • {timeAgo(rec.published_at)}
                   </div>
               </div>
            </Link>
         ))}
      </div>
    </div>
  );
};
