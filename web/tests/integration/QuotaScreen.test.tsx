import { describe, expect, it, onTestFinished, vi } from 'vitest'
import { createQueryClient } from 'strata-react'
import { keys } from '../../src/api'
import { quotaUsage } from '../../src/mocks/fixtures'
import { quotaError, quotaIsSpent, quotaNothingYet, quotaWithoutKey } from '../../src/mocks/handlers'
import { openApp, screen, within } from '../utils/render'
import { server } from '../utils/server'

describe('YouTube quota', () => {
  it('says what is used and left, what used it, and the last 30 days', async () => {
    const { user, router } = openApp('/admin/system')
    await user.click(await screen.findByRole('link', { name: /^YouTube quota/, description: /daily quota/ }))
    expect(router.state.location.pathname).toBe('/admin/quota')
    expect(await screen.findByText(/^1,712\sunits of 10,000 used today, 8,288\sunits left until the reset at \d\d:\d\d \(midnight Pacific\)\. Most went on syncing channels\.$/)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Quota used today' })).toHaveAttribute('aria-valuenow', '1712')
    const parts = screen.getByRole('table', { name: 'Today’s units by purpose' })
    expect(within(parts).getByText('Syncing channels')).toBeInTheDocument()
    expect(within(parts).getByText('Checking videos found missing')).toBeInTheDocument()
    expect(within(parts).getByText('Left')).toBeInTheDocument()
    const endpoints = screen.getByRole('grid', { name: 'Today’s calls by endpoint' })
    expect(within(endpoints).getAllByRole('row')).toHaveLength(4)
    expect(within(endpoints).getByText('playlistItems')).toBeInTheDocument()
    const days = screen.getByRole('grid', { name: 'Days that used quota, newest first' })
    const rows = within(days).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(quotaUsage.days.filter(d => d.calls).length)
    expect(rows[0]).toHaveTextContent('9 Nov 2026')
    expect(within(days).getByText('Yes')).toBeInTheDocument()                                    // the day the first full sync ran out
    expect(screen.getByRole('img', { name: /Quota units used per day/ })).toBeInTheDocument()
  })

  it('says the quota is spent once YouTube refuses a call', async () => {
    server.use(quotaIsSpent)
    openApp('/admin/quota')
    expect(await screen.findByText(/^YouTube refused a call at \d\d:\d\d because the key’s quota is spent/)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Quota used today' })).toHaveAttribute('aria-valuetext', 'Spent')
    expect(screen.getByText('YouTube has refused a call')).toBeInTheDocument()
  })

  it('says when nothing has been asked yet, and when there is no key', async () => {
    server.use(quotaNothingYet)
    const first = openApp('/admin/quota')
    expect(await screen.findByText(/^Nothing has been asked of YouTube today\. All 10,000\sunits are there/)).toBeInTheDocument()
    expect(screen.getByText('Nothing asked of YouTube yet today')).toBeInTheDocument()
    first.unmount()
    server.use(quotaWithoutKey)
    openApp('/admin/quota')
    expect(await screen.findByText(/^The server has no YouTube key/)).toBeInTheDocument()
    expect(screen.getByText('No quota used in 30 days')).toBeInTheDocument()
  })

  it('keeps the last counts when the server stops answering', async () => {
    vi.useFakeTimers({ now: Date.UTC(2026, 10, 9, 9, 0), shouldAdvanceTime: true })     // the notice gives the time alone on the same day: pin the day
    onTestFinished(() => { vi.useRealTimers() })
    const client = createQueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(keys.quota, quotaUsage, { updatedAt: Date.UTC(2026, 10, 9, 8, 50) })
    server.use(quotaError)
    openApp('/admin/quota', { client })
    expect(await screen.findByText(/These counts are from 08:50\./)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Quota used today' })).toBeInTheDocument()
  })
})
