import type { Meta, StoryObj } from '@storybook/react-vite'
import { saveSettingsFails, settingsError, settingsLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Settings',
  render: () => <AppAt route="/settings" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const General: Story = {}
export const Appearance: Story = { render: () => <AppAt route="/settings?tab=appearance" /> }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(settingsLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(settingsError) }
/** Saving fails; press Save settings to see it. */
export const SavingFails: Story = { beforeEach: ({ msw }) => msw.use(saveSettingsFails), tags: ['no-visual'] }
export const Phone: Story = { tags: ['visual-phone'] }
