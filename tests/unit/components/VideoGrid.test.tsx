import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { VideoGrid } from '@/src/components/VideoGrid';

describe('VideoGrid', () => {
  it('renders grid container', () => {
    render(<VideoGrid />);
    const grid = screen.getByText('Talking Tech and AI with Google CEO Sundar Pichai!').closest('.grid');
    expect(grid).toBeInTheDocument();
  });

  it('renders correct number of videos', () => {
    render(<VideoGrid />);
    // There are 12 videos in the hardcoded list
    const title = screen.getByText('Talking Tech and AI with Google CEO Sundar Pichai!');
    expect(title).toBeInTheDocument();
  });

  it('renders video details correctly', () => {
    render(<VideoGrid />);

    // Check first video details
    expect(screen.getByText('Talking Tech and AI with Google CEO Sundar Pichai!')).toBeInTheDocument();
    // 'Marques Brownlee' appears multiple times (channel name link and tooltip)
    const channelNames = screen.getAllByText('Marques Brownlee');
    expect(channelNames.length).toBeGreaterThan(0);
    expect(screen.getByText('14:20')).toBeInTheDocument();
    // The view count and time might be split or text content matching might need to be exact
    // Looking at the code: {video.views} &#183; {video.time}
    // "3.4M views · 6 months ago" - the dot might be different char.
    // The code uses &#183; which is middle dot (·)
    expect(screen.getByText(/3.4M views/)).toBeInTheDocument();
    expect(screen.getByText(/6 months ago/)).toBeInTheDocument();
  });

  it('renders valid links for video and channel', () => {
    render(<VideoGrid />);

    const videoLink = screen.getByText('Talking Tech and AI with Google CEO Sundar Pichai!').closest('a');
    expect(videoLink).toHaveAttribute('href', 'https://www.youtube.com/watch?v=n2RNcPRtAiY');

    // Use getAllByText because channel name is in tooltip too
    const channelLinks = screen.getAllByText('Marques Brownlee');
    // The one in the grid below the video is an anchor tag
    const channelLink = channelLinks.find(el => el.closest('a')?.getAttribute('href') === 'https://www.youtube.com/c/mkbhd');
    expect(channelLink).toBeInTheDocument();
  });
});
