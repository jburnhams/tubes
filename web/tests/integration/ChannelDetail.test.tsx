import { describe, expect, it } from 'vitest'
import { addWatchedFails, overviewError, overviewLoading } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

describe('Channel panel', () => {
  it('opens from a History row, in the URL, with the history, numbers and options', async () => {
    const { user, router } = openApp('/admin/history')
    await user.click(await screen.findByRole('button', { name: 'More about Puppet Theatre' }))
    expect(await screen.findByText(/^Watched 58\stimes \(41\svideos\) from .* to .*, across home \(50\) and work \(8\)\.$/)).toBeInTheDocument()
    expect(router.state.location.search).toBe('?open=UCsuggest000000000000002')
    expect(screen.getByText('Not in the library')).toBeInTheDocument()
    expect(screen.getByText('Made for kids')).toBeInTheDocument()
    expect(screen.getByText('Group: Puppet Theatre, Counting Songs · Entertainment, Film')).toBeInTheDocument()
    const numbers = screen.getByLabelText('Puppet Theatre in numbers')
    expect(within(numbers).getByText('120')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Watches of Puppet Theatre per month' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Puppet Theatre: the one watched most' })).toHaveAttribute('href', '/watch/wo000000000')
    expect(screen.getByRole('link', { name: 'Puppet Theatre: a favourite' })).toHaveAttribute('href', 'https://www.youtube.com/watch?v=xx000000001')
    expect(within(screen.getByRole('region', { name: 'Videos of Puppet Theatre watched most' })).getByRole('link', { name: 'A video no longer on YouTube' })).toHaveAttribute('href', 'https://www.youtube.com/watch?v=xx000000002')
    expect(screen.getByRole('link', { name: 'Open on YouTube' })).toHaveAttribute('href', 'https://www.youtube.com/channel/UCsuggest000000000000002')
    expect(screen.queryByRole('link', { name: 'Open in Tubes' })).not.toBeInTheDocument()
  })

  it('follows, adds the watched videos, and dismisses and restores the suggestion', async () => {
    const { user } = openApp('/admin/history?open=UCsuggest000000000000001')
    await user.click(await screen.findByRole('button', { name: 'Add watched videos' }))
    expect(await screen.findByText(/^Added 378\svideos of Bike Repairs to the library\.$/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Dismiss suggestion' }))
    expect(await screen.findByText('Dismissed Bike Repairs from the suggestions.')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Restore suggestion' }))
    expect(await screen.findByText('Bike Repairs is back in the suggestions.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Follow' }))
    expect(await screen.findByText('Following Bike Repairs. Its videos are being fetched.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Follow' })).not.toBeInTheDocument())
    expect(await screen.findByRole('link', { name: 'Open in Tubes' })).toHaveAttribute('href', '/channels/UCsuggest000000000000001')
    expect(mock.followed).toEqual(['UCsuggest000000000000001'])
  })

  it('opens from the Library, where a followed channel has no options to follow', async () => {
    const { user } = openApp('/admin/library')
    await user.click(await screen.findByRole('button', { name: 'More about Workshop Notes' }))
    expect(await screen.findByText(/^Followed, 6\svideos here$/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Follow' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open in Tubes' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'More about Rivers and Coasts' }))
    expect(await screen.findByText('Not in the watch history.')).toBeInTheDocument()
    expect(screen.getByText(/^\d+\svideos? in the library, not followed$/)).toBeInTheDocument()
  })

  it('opens from a suggestion with More, and closes with Less', async () => {
    const { user } = openApp('/admin/suggestions')
    await user.click(await screen.findByRole('button', { name: 'More Garden Birds' }))
    expect(await screen.findByText(/^Watched 58\stimes/)).toBeInTheDocument()
    expect(screen.getByText('Group: Making and mending · Lifestyle')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Less Garden Birds' }))
    expect(screen.queryByText(/^Watched 58\stimes/)).not.toBeInTheDocument()
  })

  it('dismisses from a suggestion\'s panel with Undo, as the list does', async () => {
    const { user } = openApp('/admin/suggestions')
    await user.click(await screen.findByRole('button', { name: 'More Garden Birds' }))
    await user.click(await screen.findByRole('button', { name: 'Dismiss suggestion' }))
    expect(screen.getByText('Dismissed Garden Birds.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(await screen.findByRole('link', { name: 'Garden Birds' })).toBeInTheDocument()
  })

  it('shows the sync a follow started on the Library page', async () => {
    const { user } = openApp('/admin/library?open=UCcoasts0000000000000004')
    await user.click(await screen.findByRole('button', { name: 'Follow' }))
    expect(await screen.findByText(/^Starting a sync of 1\schannel\.$|^Syncing 1 of 1: Rivers and Coasts\./)).toBeInTheDocument()
  })

  it('shows a dismissed suggestion as dismissed, and says why an option failed', async () => {
    server.use(addWatchedFails)
    const { user } = openApp('/admin/history?open=UCsuggest000000000000001')
    mock.suggestions = mock.suggestions.map(x => (x.title === 'Bike Repairs' ? { ...x, dismissed: '2026-11-01T00:00:00+00:00', subscribers: null } : x))
    await user.click(await screen.findByRole('button', { name: 'Add watched videos' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('says when it cannot be read, and waits with a skeleton', async () => {
    server.use(overviewError)
    const { user, unmount } = openApp('/admin/history')
    await user.click(await screen.findByRole('button', { name: 'More about Bike Repairs' }))
    expect((await screen.findAllByText(/could not answer|try again/i)).length).toBeGreaterThan(0)
    unmount()
    server.use(overviewLoading)
    openApp('/admin/history?open=UCsuggest000000000000001')
    await screen.findByRole('table', { name: 'Channels watched most in this timeframe' })
    expect(screen.queryByText(/^Watched /)).not.toBeInTheDocument()
  })
})
