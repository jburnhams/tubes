import type { Meta, StoryObj } from '@storybook/react-vite'
import { groups } from '../src/mocks/fixtures'
import { groupsEmpty, groupsError, groupsLoading, videosLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Watching/Groups',
  render: () => <AppAt route="/groups" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const group = `/groups/${groups[0].id}`

/** Every group, largest first; one has no picture. The real server picks another picture each time. */
export const Ready: Story = {}
export const Empty: Story = { beforeEach: ({ msw }) => msw.use(groupsEmpty) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(groupsLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(groupsError) }
export const Phone: Story = { tags: ['visual-phone'] }

/** One group's videos, those that represent it best first, each with its channel. */
export const Group: Story = { render: () => <AppAt route={group} /> }
export const GroupVideosLoading: Story = { render: () => <AppAt route={group} />, beforeEach: ({ msw }) => msw.use(videosLoading) }
export const NoSuchGroup: Story = { render: () => <AppAt route="/groups/99" /> }
