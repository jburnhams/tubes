import type { Meta, StoryObj } from '@storybook/react-vite'
import { quotaError, quotaIsSpent, quotaLoading, quotaNothingYet, quotaWithoutKey } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/YouTube quota',
  render: () => <AppAt route="/admin/quota" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
/** YouTube refused a call: nothing is left until midnight Pacific, whoever spent it. */
export const Spent: Story = { beforeEach: ({ msw }) => msw.use(quotaIsSpent) }
/** A key, and nothing asked of YouTube yet today. */
export const NothingYet: Story = { beforeEach: ({ msw }) => msw.use(quotaNothingYet) }
export const NoKey: Story = { beforeEach: ({ msw }) => msw.use(quotaWithoutKey) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(quotaLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(quotaError) }
export const Phone: Story = { tags: ['visual-phone'] }
