import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChannelModal } from '@/src/components/ChannelModal';
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

describe('ChannelModal', () => {
  it('renders nothing when channel is null', () => {
    const handleClose = vi.fn();
    const { container } = render(<ChannelModal channel={null} onClose={handleClose} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders channel details when channel is provided', () => {
    const handleClose = vi.fn();
    render(<ChannelModal channel={mockChannel} onClose={handleClose} />);

    expect(screen.getByText('Test Channel')).toBeInTheDocument();
    expect(screen.getByText('@testchannel')).toBeInTheDocument();
    expect(screen.getByText('A test channel description')).toBeInTheDocument();
    expect(screen.getByText('US')).toBeInTheDocument();

    // Should use best_thumbnail_url
    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('src', 'https://example.com/big-thumb.jpg');
  });

  it('falls back to thumbnail_url if best_thumbnail_url is missing', () => {
    const channelWithoutBigThumb = { ...mockChannel, best_thumbnail_url: null };
    const handleClose = vi.fn();
    render(<ChannelModal channel={channelWithoutBigThumb} onClose={handleClose} />);

    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('src', 'https://example.com/thumb.jpg');
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<ChannelModal channel={mockChannel} onClose={handleClose} />);

    const closeButton = screen.getByLabelText('Close modal');
    fireEvent.click(closeButton);
    expect(handleClose).toHaveBeenCalled();
  });

  it('calls onClose when backdrop is clicked', () => {
    const handleClose = vi.fn();
    render(<ChannelModal channel={mockChannel} onClose={handleClose} />);

    const backdrop = screen.getByTestId('channel-modal-backdrop');
    fireEvent.click(backdrop);
    expect(handleClose).toHaveBeenCalled();
  });

  it('does not call onClose when content is clicked', () => {
    const handleClose = vi.fn();
    render(<ChannelModal channel={mockChannel} onClose={handleClose} />);

    const content = screen.getByTestId('channel-modal-content');
    fireEvent.click(content);
    expect(handleClose).not.toHaveBeenCalled();
  });
});
