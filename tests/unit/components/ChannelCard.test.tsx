import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChannelCard } from '@/src/components/ChannelCard';
import { Channel } from '@/src/types/youtube';
import { describe, it, expect, vi } from 'vitest';

const mockChannel: Channel = {
  youtube_id: '123',
  title: 'Test Channel',
  description: 'A test channel description',
  custom_url: '@testchannel',
  thumbnail_url: 'https://example.com/thumb.jpg',
  best_thumbnail_url: 'https://example.com/big-thumb.jpg',
  published_at: '2023-01-01T00:00:00Z',
  country: 'US',
};

describe('ChannelCard', () => {
  it('renders channel information', () => {
    const handleClick = vi.fn();
    render(<ChannelCard channel={mockChannel} onClick={handleClick} />);

    expect(screen.getByText('Test Channel')).toBeInTheDocument();
    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('src', 'https://example.com/thumb.jpg');
    expect(img).toHaveAttribute('alt', 'Test Channel');
  });

  it('calls onClick with channel data when clicked', () => {
    const handleClick = vi.fn();
    render(<ChannelCard channel={mockChannel} onClick={handleClick} />);

    fireEvent.click(screen.getByTestId('channel-card'));
    expect(handleClick).toHaveBeenCalledWith(mockChannel);
  });
});
