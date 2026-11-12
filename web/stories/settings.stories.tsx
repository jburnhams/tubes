import type { Meta, StoryObj } from '@storybook/react-vite'
import { saveSettingsFails, settingsError, settingsLoading, shownError, shownLoading, shownSet } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/Settings',
  render: () => <AppAt route="/admin/settings" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const General: Story = {}
/** Which videos the watching side shows, as a new server has it: no length limits. */
export const ShownVideos: Story = { render: () => <AppAt route="/admin/settings?tab=shown" /> }
/** Short videos and past streams left out. */
export const ShownVideosSet: Story = { render: () => <AppAt route="/admin/settings?tab=shown" />, beforeEach: ({ msw }) => msw.use(shownSet) }
export const ShownVideosLoading: Story = { render: () => <AppAt route="/admin/settings?tab=shown" />, beforeEach: ({ msw }) => msw.use(shownLoading) }
export const ShownVideosError: Story = { render: () => <AppAt route="/admin/settings?tab=shown" />, beforeEach: ({ msw }) => msw.use(shownError) }
export const Appearance: Story = { render: () => <AppAt route="/admin/settings?tab=appearance" /> }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(settingsLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(settingsError) }
/** Saving fails; press Save settings to see it. */
export const SavingFails: Story = { beforeEach: ({ msw }) => msw.use(saveSettingsFails), tags: ['no-visual'] }
export const Phone: Story = { tags: ['visual-phone'] }
