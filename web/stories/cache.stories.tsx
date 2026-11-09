import type { Meta, StoryObj } from '@storybook/react-vite'
import { cacheEmpty, cacheError, cacheLoading, cacheNearlyFull, dropFails, evictFails, pinFails } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Cache',
  render: () => <AppAt route="/cache" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
export const SortedBySize: Story = { render: () => <AppAt route="/cache?sort=bytes.desc" /> }
/** Over the 95% line: the meter crosses Trimming and the finding says what goes next. */
export const OverTheLine: Story = { beforeEach: ({ msw }) => msw.use(cacheNearlyFull) }
export const Empty: Story = { beforeEach: ({ msw }) => msw.use(cacheEmpty) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(cacheLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(cacheError) }
/** Pin, Delete and Trim now each fail; press one to see what it says. */
export const ActionsFail: Story = { beforeEach: ({ msw }) => msw.use(pinFails, dropFails, evictFails), tags: ['no-visual'] }
export const Phone: Story = { tags: ['visual-phone'] }
