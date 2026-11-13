import { afterEach, describe, expect, it } from 'vitest'
import { act } from 'react'
import { http, HttpResponse } from 'msw'
import { installFakeIntersectionObserver } from 'strata-react/testing'
import { playsLong, viewingEmpty, viewingError } from '../../src/mocks/handlers'
import { channelVisits, playSummary } from '../../src/mocks/fixtures'
import { openApp, screen, waitFor, within } from '../utils/render'
import { server } from '../utils/server'

const plays = () => screen.findByRole('list', { name: 'Plays, newest first' })

describe('Viewing', () => {
  let observer: ReturnType<typeof installFakeIntersectionObserver> | undefined
  afterEach(() => { observer?.uninstall(); observer = undefined })

  it('says what was played in the last 30 days, how it ended and where it started', async () => {
    openApp('/admin/viewing')
    expect(await screen.findByText(/^46\splays of 29\svideos in the last 30\sdays, 20 watched to the end, 8\sh 43\smin in all\. Most started from Home \(18\)\.$/)).toBeInTheDocument()
    expect(screen.getByText('43% of plays · 90% and more seen')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()                                   // short looks and never started, together
    expect(screen.getByRole('table', { name: 'Where plays were started' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Viewing' })).toHaveAttribute('aria-current', 'page')
  })

  it('lists every play newest first, each opening to all that was kept of it, open in the URL', async () => {
    const { user, router } = openApp('/admin/viewing')
    const list = await plays()
    expect(within(list).getAllByRole('listitem')).toHaveLength(8)
    const first = within(list).getByRole('button', { name: /^Building a bird box/ })
    expect(first).toHaveTextContent('97%')
    expect(first).toHaveTextContent('Watched to the end')
    await user.click(first)
    expect(router.state.location.search).toBe('?open=8')
    await user.click(within(within(list).getAllByRole('listitem')[7]).getByRole('button'))      // the oldest: from Up next
    expect(router.state.location.search).toBe('?open=8&open=1')
    const terms = (label: string) => screen.getAllByText(label, { selector: 'dt' }).map(t => t.nextElementSibling?.textContent)
    expect(terms('Started from')[0]).toBe('Home')
    expect(terms('Started from')[1]).toMatch(/^Up next: \S/)
    expect(terms('Place in that list')).toEqual(['1', '1'])
    expect(terms('Last report')[0]).toMatch(/2026/)
    expect(screen.getByRole('link', { name: 'Building a bird box' })).toHaveAttribute('href', '/watch/wo000000000')
    expect(screen.getAllByRole('link', { name: 'Workshop Notes' })[0]).toHaveAttribute('href', '/channels/UCworkshop00000000000001')
  })

  it('names the search words, the channel, and what was never started', async () => {
    const { user } = openApp('/admin/viewing?open=5&open=4&open=3')
    await plays()
    const terms = (label: string) => screen.getAllByText(label, { selector: 'dt' }).map(t => t.nextElementSibling?.textContent)
    expect(terms('Started from')).toEqual(['Search: “rock pools”', 'A channel’s page: Workshop Notes', 'A link or the address bar'])
    expect(terms('Last report')[2]).toBe('None: the picture never started')
    expect(terms('Place in that list')[2]).toBe('–')
    await user.click(screen.getByRole('button', { name: /^Building a bird box/ }))
    expect(terms('Stopped at')).toHaveLength(4)
  })

  it('filters by how a play ended and where it started, kept in the URL', async () => {
    const { user, router } = openApp('/admin/viewing')
    await plays()
    await user.selectOptions(screen.getByRole('combobox', { name: 'How it ended' }), 'Part watched')
    await waitFor(async () => expect(within(await plays()).getAllByRole('listitem')).toHaveLength(3))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Started from' }), 'Search')
    await waitFor(async () => expect(within(await plays()).getAllByRole('listitem')).toHaveLength(1))
    expect(router.state.location.search).toBe('?outcome=partial&source=search')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Started from' }), 'Up next')
    expect(await screen.findByText('No plays like that')).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'How it ended' }), 'Any way')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Started from' }), 'Anywhere')
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('reads older plays a page at a time', async () => {
    server.use(playsLong)
    observer = installFakeIntersectionObserver()
    openApp('/admin/viewing')
    const list = await plays()
    await waitFor(() => expect(within(list).getAllByRole('listitem').length).toBeGreaterThan(0))
    act(() => { observer!.scrollToEnd() })
    await waitFor(() => expect(screen.getByText('That is every play kept.')).toBeInTheDocument(), { timeout: 3000 })
  })

  it('lists the channel pages visited and where from', async () => {
    openApp('/admin/viewing')
    const visits = await screen.findByRole('list', { name: 'Channel pages visited, newest first' })
    expect(within(visits).getByRole('link', { name: 'Workshop Notes' })).toHaveAttribute('href', '/channels/UCworkshop00000000000001')
    expect(within(visits).getByText(/from A video’s page: Building a bird box$/)).toBeInTheDocument()
    expect(within(visits).getByText(/from The side rail$/)).toBeInTheDocument()
    expect(within(visits).getByRole('link', { name: 'UCgone000000000000000009' })).toBeInTheDocument()
  })

  it('says when nothing has been played yet', async () => {
    server.use(...viewingEmpty)
    openApp('/admin/viewing')
    expect(await screen.findByText(/^Nothing has been played here in the last 30\sdays\./)).toBeInTheDocument()
    expect(screen.getByText('Nothing played yet')).toBeInTheDocument()
    expect(screen.getByText('No channel pages visited yet')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Where plays were started' })).toBeNull()
  })

  it('says the server could not answer', async () => {
    server.use(...viewingError)
    openApp('/admin/viewing')
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Try again' }).length).toBeGreaterThanOrEqual(3))
  })

  it('counts time under a minute in seconds and a source it does not know as somewhere else', async () => {
    server.use(
      http.get('*/api/plays/summary', () => HttpResponse.json({ ...playSummary, seconds: 40, sources: { mystery: { plays: 46, full: 20 } } })),
      http.get('*/api/plays', () => HttpResponse.json({ items: [
        { id: 2, video_id: 'yy000000000', title: null, channel_id: 'UCyy', channel: null, thumbnail: null, at: '2026-11-09T10:30:00+00:00', updated: '2026-11-09T10:31:00+00:00', source: 'home', detail: null, detail_title: null, rank: 0, length: null, watched: 50, position: 50, outcome: 'partial' },
        { id: 1, video_id: 'xx000000000', title: null, channel_id: null, channel: null, thumbnail: null, at: '2026-11-09T10:00:00+00:00', updated: null, source: 'other', detail: null, detail_title: null, rank: null, length: null, watched: null, position: null, outcome: 'none' },
      ], has_more: false })),
    )
    const { user } = openApp('/admin/viewing')
    expect(await screen.findByText(/40\ss in all\. Most started from Somewhere else \(46\)\.$/)).toBeInTheDocument()
    const row = within(await plays()).getByRole('button', { name: /^xx000000000/ })
    expect(row).toHaveTextContent('–')
    await user.click(row)
    const terms = (label: string) => screen.getAllByText(label, { selector: 'dt' }).map(t => t.nextElementSibling?.textContent)
    expect(terms('Seen')).toEqual(['Not kept for this play'])
    expect(terms('Channel')).toEqual(['–'])
    expect(terms('Started from')).toEqual(['Somewhere else'])
    await user.click(within(await plays()).getByRole('button', { name: /^yy000000000/ }))      // a channel with no name, and seconds seen of an unknown length
    expect(terms('Channel')).toEqual(['UCyy', '–'])
    expect(terms('Seen')).toEqual(['0:50', 'Not kept for this play'])
  })

  it('reads older channel visits after the last one held', async () => {
    server.use(http.get('*/api/channel-views', ({ request }) => {
      const after = new URL(request.url).searchParams.get('after')
      return HttpResponse.json(after ? { items: [{ ...channelVisits[3], id: 0, title: 'An older visit' }], has_more: false } : { items: channelVisits, has_more: true })
    }))
    observer = installFakeIntersectionObserver()
    const { user } = openApp('/admin/viewing')
    await screen.findByRole('list', { name: 'Channel pages visited, newest first' })
    await user.click(await screen.findByRole('button', { name: 'Show older visits' }))
    expect(await screen.findByRole('link', { name: 'An older visit' })).toBeInTheDocument()
  })
})
