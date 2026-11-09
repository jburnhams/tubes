import { useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { useQueryClient } from '@tanstack/react-query'
import { keys } from '../src/api'
import { systemStatus } from '../src/mocks/fixtures'
import { systemError, systemInTrouble, systemLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/System',
  render: () => <AppAt route="/admin/system" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
/** yt-dlp missing, no YouTube key, the disk nearly full: the finding names the first. */
export const InTrouble: Story = { beforeEach: ({ msw }) => msw.use(systemInTrouble) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(systemLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(systemError) }
export const Phone: Story = { tags: ['visual-phone'] }

/** Puts readings taken at 08:50 into the cache, as an earlier poll would have. */
function EarlierReadings({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  useState(() => client.setQueryData(keys.system, systemStatus, { updatedAt: Date.UTC(2026, 10, 9, 8, 50) }))
  return children
}

/** The server stopped answering after a good poll: the readings stay, with how old they are. */
export const ReadingsOld: Story = {
  beforeEach: ({ msw }) => msw.use(systemError),
  decorators: [Story => <EarlierReadings><Story /></EarlierReadings>],
}
