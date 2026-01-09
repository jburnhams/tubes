import React, { useEffect, useRef } from 'react';
import { TubePlayer } from '@jburnhams/tube-ts';
import 'shaka-player/dist/controls.css';

interface TubePlayerWrapperProps {
  videoId: string;
  sessionId?: string;
}

export const TubePlayerWrapper: React.FC<TubePlayerWrapperProps> = ({ videoId, sessionId }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<TubePlayer | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Use a unique ID for the container if needed by TubePlayer constructor
    const containerId = 'tube-player-container';
    containerRef.current.id = containerId;

    const player = new TubePlayer(containerId);
    playerRef.current = player;

    const initAndLoad = async () => {
      try {
        await player.initialize({
          sessionId: sessionId,
        });
        await player.loadVideo(videoId);
      } catch (error) {
        console.error('Failed to initialize or load video in TubePlayer', error);
      }
    };

    initAndLoad();

    return () => {
      if (playerRef.current) {
        playerRef.current.destroy();
        playerRef.current = null;
      }
    };
  }, [videoId, sessionId]);

  return (
    <div
      ref={containerRef}
      className="w-full h-full bg-black"
    />
  );
};
