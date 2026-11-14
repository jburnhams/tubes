import type { Meta, StoryObj } from '@storybook/react-vite'
import { viewingEmpty, viewingError, viewingLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/Viewing',
  render: () => <AppAt route="/admin/viewing" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** The last 30 days in numbers, where plays were started, every play newest first, and the channel pages visited. */
export const Ready: Story = {}
/** Two plays opened in place: one from Home watched to the end, one from Up next, with all that was kept of each. */
export const PlaysOpen: Story = { render: () => <AppAt route="/admin/viewing?open=8&open=1" /> }
/** Only part-watched plays from a search. */
export const Filtered: Story = { render: () => <AppAt route="/admin/viewing?outcome=partial&source=search" /> }
export const NothingPlayed: Story = { beforeEach: ({ msw }) => msw.use(...viewingEmpty) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(...viewingLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(...viewingError) }
export const Phone: Story = { tags: ['visual-phone'] }
