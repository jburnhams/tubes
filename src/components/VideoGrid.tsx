import React from 'react';

// Hardcoded data matching youtube.html content
const videos = [
    {
        id: 'n2RNcPRtAiY',
        title: 'Talking Tech and AI with Google CEO Sundar Pichai!',
        thumbnail: '/thumbnails/thumbnail-1.webp',
        duration: '14:20',
        channelName: 'Marques Brownlee',
        channelUrl: 'https://www.youtube.com/c/mkbhd',
        channelPicture: '/channel-pictures/channel-1.jpeg',
        subscribers: '16.6M',
        views: '3.4M views',
        time: '6 months ago',
        videoUrl: 'https://www.youtube.com/watch?v=n2RNcPRtAiY'
    },
    {
        id: 'mP0RAo9SKZk',
        title: 'Try Not to Laugh Challenge #9',
        thumbnail: '/thumbnails/thumbnail-2.webp',
        duration: '8:22',
        channelName: 'Markiplier',
        channelUrl: 'https://www.youtube.com/c/markiplier',
        channelPicture: '/channel-pictures/channel-2.jpeg',
        subscribers: '34.3M',
        views: '19M views',
        time: '4 years ago',
        videoUrl: 'https://www.youtube.com/watch?v=mP0RAo9SKZk'
    },
    {
        id: 'FgjPQQeTh1w',
        title: 'Crazy Tik Toks Taken Moments Before DISASTER',
        thumbnail: '/thumbnails/thumbnail-3.webp',
        duration: '9:13',
        channelName: 'SSSniperWolf',
        channelUrl: 'https://www.youtube.com/user/SSSniperWolf',
        channelPicture: '/channel-pictures/channel-3.jpeg',
        subscribers: '33.2M',
        views: '12M views',
        time: '1 year ago',
        videoUrl: 'https://www.youtube.com/watch?v=FgjPQQeTh1w'
    },
    {
        id: '094y1Z2wpJg',
        title: 'The Simplest Math Problem No One Can Solve - Collatz Conjecture',
        thumbnail: '/thumbnails/thumbnail-4.webp',
        duration: '22:09',
        channelName: 'Veritasium',
        channelUrl: 'https://www.youtube.com/c/veritasium',
        channelPicture: '/channel-pictures/channel-4.jpeg',
        subscribers: '13.3M',
        views: '18M views',
        time: '4 months ago',
        videoUrl: 'https://www.youtube.com/watch?v=094y1Z2wpJg'
    },
    {
        id: '86CQq3pKSUw',
        title: "Kadane's Algorithm to Maximum Sum Subarray Problem",
        thumbnail: '/thumbnails/thumbnail-5.webp',
        duration: '11:17',
        channelName: 'CS Dojo',
        channelUrl: 'https://www.youtube.com/c/CSDojo',
        channelPicture: '/channel-pictures/channel-5.jpeg',
        subscribers: '1.89M',
        views: '519K views',
        time: '5 years ago',
        videoUrl: 'https://www.youtube.com/watch?v=86CQq3pKSUw'
    },
    {
        id: 'yXWw0_UfSFg',
        title: 'Anything You Can Fit In The Circle I’ll Pay For',
        thumbnail: '/thumbnails/thumbnail-6.webp',
        duration: '19:59',
        channelName: 'MrBeast',
        channelUrl: 'https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA',
        channelPicture: '/channel-pictures/channel-6.jpeg',
        subscribers: '129M',
        views: '141M views',
        time: '1 year ago',
        videoUrl: 'https://www.youtube.com/watch?v=yXWw0_UfSFg'
    },
    {
        id: 'fNVa1qMbF9Y',
        title: "Why Planes Don't Fly Over Tibet",
        thumbnail: '/thumbnails/thumbnail-7.webp',
        duration: '10:13',
        channelName: 'RealLifeLore',
        channelUrl: 'https://www.youtube.com/channel/UCP5tjEmvPItGyLhmjdwP7Ww',
        channelPicture: '/channel-pictures/channel-7.jpeg',
        subscribers: '6.56M',
        views: '6.6M views',
        time: '1 year ago',
        videoUrl: 'https://www.youtube.com/watch?v=fNVa1qMbF9Y'
    },
    {
        id: 'lFm4EM1juls',
        title: "Inside The World's Biggest Passenger Plane",
        thumbnail: '/thumbnails/thumbnail-8.webp',
        duration: '7:12',
        channelName: 'Tech Vision',
        channelUrl: 'https://www.youtube.com/channel/UCHAK6CyegY22Zj2GWrcaIxg',
        channelPicture: '/channel-pictures/channel-8.jpeg',
        subscribers: '798K',
        views: '3.7M views',
        time: '10 months ago',
        videoUrl: 'https://www.youtube.com/watch?v=lFm4EM1juls'
    },
    {
        id: 'ixmxOlcrlUc',
        title: 'The SECRET to Super Human STRENGTH',
        thumbnail: '/thumbnails/thumbnail-9.webp',
        duration: '13:17',
        channelName: 'ThenX',
        channelUrl: 'https://www.youtube.com/c/OFFICIALTHENXSTUDIOS',
        channelPicture: '/channel-pictures/channel-9.jpeg',
        subscribers: '7.56M',
        views: '20M views',
        time: '3 year ago',
        videoUrl: 'https://www.youtube.com/watch?v=ixmxOlcrlUc'
    },
    {
        id: 'R2vXbFp5C9o',
        title: "How The World's Largest Cruise Ship Makes 30,000 Meals Every Day",
        thumbnail: '/thumbnails/thumbnail-10.webp',
        duration: '7:53',
        channelName: 'Business Insider',
        channelUrl: 'https://www.youtube.com/user/businessinsider',
        channelPicture: '/channel-pictures/channel-10.jpeg',
        subscribers: '7.36M',
        views: '14M views',
        time: '1 year ago',
        videoUrl: 'https://www.youtube.com/watch?v=R2vXbFp5C9o'
    },
    {
        id: '0nZuYyXET3s',
        title: "Dubai's Crazy Underwater Train and Other Things #Only in Dubai",
        thumbnail: '/thumbnails/thumbnail-11.webp',
        duration: '4:10',
        channelName: 'Destination Tips',
        channelUrl: 'https://www.youtube.com/c/Destinationtips',
        channelPicture: '/channel-pictures/channel-11.jpeg',
        subscribers: '279K',
        views: '3M views',
        time: '1 year ago',
        videoUrl: 'https://www.youtube.com/watch?v=0nZuYyXET3s'
    },
    {
        id: '9iMGFqMmUFs',
        title: "What would happen if you didn’t drink water? - Mia Nacamulli",
        thumbnail: '/thumbnails/thumbnail-12.webp',
        duration: '4:51',
        channelName: 'TED-Ed',
        channelUrl: 'https://www.youtube.com/teded',
        channelPicture: '/channel-pictures/channel-12.jpeg',
        subscribers: '18.1M',
        views: '12M views',
        time: '5 years ago',
        videoUrl: 'https://www.youtube.com/watch?v=9iMGFqMmUFs'
    }
];

export const VideoGrid: React.FC = () => {
    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 gap-y-10">
            {videos.map((video) => (
                <div key={video.id} className="flex flex-col cursor-pointer">
                    <div className="relative mb-3">
                        <a href={video.videoUrl} target="_blank" rel="noopener noreferrer" className="block relative">
                            <img className="w-full rounded-xl object-cover aspect-video hover:rounded-none transition-all duration-200" src={video.thumbnail} alt={video.title} />
                             <div className="absolute bottom-2 right-2 bg-black/80 text-white text-xs font-medium px-1.5 py-0.5 rounded">
                                {video.duration}
                            </div>
                        </a>
                    </div>
                    <div className="grid grid-cols-[36px_1fr] gap-3">
                        <div className="relative group">
                            <a href={video.channelUrl} target="_blank" rel="noopener noreferrer">
                                <img className="rounded-full w-9 h-9 object-cover" src={video.channelPicture} alt={video.channelName} />
                            </a>
                            {/* Tooltip */}
                            <div className="absolute top-10 left-0 bg-white border border-gray-200 shadow-lg rounded-lg p-3 w-48 z-50 hidden group-hover:flex items-center gap-3">
                                <img className="w-10 h-10 rounded-full" src={video.channelPicture} alt={video.channelName} />
                                <div>
                                    <p className="font-bold text-sm text-gray-900 line-clamp-1">{video.channelName}</p>
                                    <p className="text-xs text-gray-500">{video.subscribers} subscribers</p>
                                </div>
                            </div>
                        </div>
                        <div className="flex flex-col">
                            <a href={video.videoUrl} target="_blank" rel="noopener noreferrer" className="text-sm font-bold text-gray-900 leading-5 mb-1 line-clamp-2 hover:text-blue-600" title={video.title}>
                                {video.title}
                            </a>
                            <a href={video.channelUrl} target="_blank" rel="noopener noreferrer" className="text-xs text-gray-600 hover:text-gray-900 transition-colors">
                                {video.channelName}
                            </a>
                            <div className="text-xs text-gray-600">
                                {video.views} &#183; {video.time}
                            </div>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
};
