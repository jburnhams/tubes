import type { Meta, StoryObj } from '@storybook/react-vite'
import { channelsLoading, videosError, videosLoading, videosNone } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Watching/Home',
  render: () => <AppAt route="/" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
/** Before the first sync: says where to make one. */
export const NoVideos: Story = { beforeEach: ({ msw }) => msw.use(videosNone) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(videosLoading, channelsLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(videosError) }
/** On a phone the rail starts folded to icons. */
export const Phone: Story = { tags: ['visual-phone'] }
