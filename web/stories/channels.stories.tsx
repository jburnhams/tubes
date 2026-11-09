import type { Meta, StoryObj } from '@storybook/react-vite'
import { channels } from '../src/mocks/fixtures'
import { channelsEmpty, channelsError, channelsLoading, videosLaterPageError, videosLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Channels',
  render: () => <AppAt route="/channels" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const workshop = `/channels/${channels.find(c => c.title === 'Workshop Notes')!.id}`

export const Ready: Story = {}
export const Empty: Story = { beforeEach: ({ msw }) => msw.use(channelsEmpty) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(channelsLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(channelsError) }
export const Phone: Story = { tags: ['visual-phone'] }

/** One channel's videos, newest first. */
export const Channel: Story = { render: () => <AppAt route={workshop} /> }
export const ChannelVideosLoading: Story = { render: () => <AppAt route={workshop} />, beforeEach: ({ msw }) => msw.use(videosLoading) }
/** A long channel whose later pages fail; scroll to the end to see Try again. */
export const ChannelLaterPageFails: Story = { render: () => <AppAt route={workshop} />, beforeEach: ({ msw }) => msw.use(videosLaterPageError), tags: ['no-visual'] }
export const NoSuchChannel: Story = { render: () => <AppAt route="/channels/UCgone" /> }
