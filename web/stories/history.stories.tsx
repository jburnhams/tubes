import type { Meta, StoryObj } from '@storybook/react-vite'
import { historyError, historyLoading, historyNone, historyOneAccount } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/History',
  render: () => <AppAt route="/admin/history" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** The last 12 months, by month (one quiet month falls to zero), with the top channels and videos. */
export const Ready: Story = {}
/** The last 30 days, by day. */
export const LastMonth: Story = { render: () => <AppAt route="/admin/history?range=30d" /> }
/** A year before the history: nothing watched then. */
export const NothingThen: Story = { render: () => <AppAt route="/admin/history?range=2018" /> }
export const OneAccount: Story = { beforeEach: ({ msw }) => msw.use(historyOneAccount) }
export const NoHistory: Story = { beforeEach: ({ msw }) => msw.use(historyNone) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(historyLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(historyError) }
export const Phone: Story = { tags: ['visual-phone'] }
/** A channel opened in place: the shared channel panel (its history, numbers and options). */
export const ChannelOpen: Story = { render: () => <AppAt route="/admin/history?open=UCsuggest000000000000002" /> }
