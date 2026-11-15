import type { Meta, StoryObj } from '@storybook/react-vite'
import { plexBrowseLoading, plexError, plexLoading, plexManyFilms, plexNotSetUp, plexUnreachable } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/Plex',
  render: () => <AppAt route="/admin/plex" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
/** The TV library, narrowed to nothing but what is listed. */
export const Shows: Story = { render: () => <AppAt route="/admin/plex?section=2" /> }
/** A genre and a rating chosen: the listing, and its name as a channel, follow them. */
export const Filtered: Story = { render: () => <AppAt route="/admin/plex?genre=1&rating=gb%2FU" /> }
/** A library long enough to page through. */
export const ManyFilms: Story = { beforeEach: ({ msw }) => msw.use(plexManyFilms) }
export const NotSetUp: Story = { beforeEach: ({ msw }) => msw.use(plexNotSetUp) }
export const Unreachable: Story = { beforeEach: ({ msw }) => msw.use(plexUnreachable) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(plexLoading) }
export const ListingLoading: Story = { beforeEach: ({ msw }) => msw.use(plexBrowseLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(plexError) }
export const Phone: Story = { tags: ['visual-phone'] }
