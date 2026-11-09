import type { Meta, StoryObj } from '@storybook/react-vite'
import { videosError, videosLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Search',
  render: () => <AppAt route="/search?q=the" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Results: Story = {}
export const NoWords: Story = { render: () => <AppAt route="/search" /> }
export const NoMatch: Story = { render: () => <AppAt route="/search?q=zebra" /> }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(videosLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(videosError) }
