import type { Meta, StoryObj } from '@storybook/react-vite'
import { playFails, playLoading, streamIn, videoLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Watching/Watch',
  render: () => <AppAt route="/watch/wo000000000" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** A saved copy plays at once (the test card, src/mocks/testcard.ts). Shot by the visual suite as the watch route's `playing` state, held on its first frame; here it plays. */
export const Playing: Story = { tags: ['no-visual'] }
/** The fetch has started; the frame says what it is waiting for. */
export const Fetching: Story = { beforeEach: ({ msw }) => msw.use(...streamIn('fetching')) }
export const Failed: Story = { beforeEach: ({ msw }) => msw.use(...streamIn('failed')) }
export const Refused: Story = { beforeEach: ({ msw }) => msw.use(playFails) }
export const Starting: Story = { beforeEach: ({ msw }) => msw.use(playLoading) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(videoLoading) }
export const NoSuchVideo: Story = { render: () => <AppAt route="/watch/zzzzzzzzzzz" /> }
export const Phone: Story = { tags: ['visual-phone'], beforeEach: ({ msw }) => msw.use(...streamIn('fetching')) }
