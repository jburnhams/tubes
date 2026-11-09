import type { Meta, StoryObj } from '@storybook/react-vite'
import { addFails, channelsError, channelsLoading, libraryFirstVisit, libraryNoKey, removeChannelFails, syncFails, syncIn } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/Library',
  render: () => <AppAt route="/admin/library" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** No sync since the server started: the channels, each in its state. */
export const Ready: Story = {}
/** A sync part way: what it is on and how many new videos so far; the sync buttons wait. */
export const Syncing: Story = { beforeEach: ({ msw }) => msw.use(syncIn('running')) }
export const Finished: Story = { beforeEach: ({ msw }) => msw.use(syncIn('done')) }
/** The last sync ran out of quota on one channel: it is named, with YouTube's reason. */
export const FinishedWithFailures: Story = { beforeEach: ({ msw }) => msw.use(syncIn('failed')) }
/** The server has no YouTube key: the finding says what to do, and nothing that needs one is offered. */
export const NoKey: Story = { beforeEach: ({ msw }) => msw.use(libraryNoKey) }
export const FirstVisit: Story = { beforeEach: ({ msw }) => msw.use(...libraryFirstVisit) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(channelsLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(channelsError) }
/** Adding, syncing and removing each fail; press one to see what it says. */
export const ActionsFail: Story = { beforeEach: ({ msw }) => msw.use(addFails, syncFails, removeChannelFails), tags: ['no-visual'] }
export const Phone: Story = { tags: ['visual-phone'] }
