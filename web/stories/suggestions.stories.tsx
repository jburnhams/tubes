import type { Meta, StoryObj } from '@storybook/react-vite'
import { addWatchedFails, followFails, relatedNotAsked, suggestionsError, suggestionsFirstVisit, suggestionsLoading, suggestionsNoKey, suggestionsRelatedOnly, summaryLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Admin/Suggestions',
  render: () => <AppAt route="/admin/suggestions" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** Channels from two histories, best first: the first is active, with the keys that answer it. */
export const Ready: Story = {}
/** Most pointed at by the followed and most watched channels first: the channels their watch pages keep listing. */
export const MostPointedAt: Story = { render: () => <AppAt route="/admin/suggestions?order=suggested" /> }
/** No history imported yet: only what the followed channels point at, with the import form below. */
export const RelatedOnly: Story = { beforeEach: ({ msw }) => msw.use(...suggestionsRelatedOnly), render: () => <AppAt route="/admin/suggestions?order=suggested" /> }
/** YouTube has not been asked about related channels yet: the finding says the server will. */
export const RelatedNotAsked: Story = { beforeEach: ({ msw }) => msw.use(relatedNotAsked) }
/** One group: its name can be changed here. */
export const OneGroup: Story = { render: () => <AppAt route="/admin/suggestions?group=2" /> }
export const Dismissed: Story = { render: () => <AppAt route="/admin/suggestions?view=dismissed" /> }
/** No history yet: the page is the import form, saying where Takeout puts the file. */
export const FirstVisit: Story = { beforeEach: ({ msw }) => msw.use(suggestionsFirstVisit) }
/** The server has no YouTube key: only dismissing is offered. */
export const NoKey: Story = { beforeEach: ({ msw }) => msw.use(suggestionsNoKey) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(summaryLoading) }
export const ListLoading: Story = { beforeEach: ({ msw }) => msw.use(suggestionsLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(suggestionsError) }
/** Following and adding fail; press one to see what it says. */
export const ActionsFail: Story = { beforeEach: ({ msw }) => msw.use(followFails, addWatchedFails), tags: ['no-visual'] }
export const Phone: Story = { tags: ['visual-phone'] }
