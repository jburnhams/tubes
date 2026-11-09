import type { Meta, StoryObj } from '@storybook/react-vite'
import { libraryNeverSynced, shuffleEmpty, shuffleError, shuffleLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Browse',
  render: () => <AppAt route="/" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
/** Before the first sync: the finding says where to make one. */
export const NeverSynced: Story = { beforeEach: ({ msw }) => msw.use(libraryNeverSynced, shuffleEmpty) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(shuffleLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(shuffleError) }
export const Phone: Story = { tags: ['visual-phone'] }
