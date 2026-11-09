import { afterEach, describe, expect, it } from 'vitest'
import { installFakeIntersectionObserver } from 'strata-react/testing'
import { channels } from '../../src/mocks/fixtures'
import { channelsLoading, videosError, videosFrom, videosLaterPageError, videosLaterPageLoading, videosLong, videosNone } from '../../src/mocks/handlers'
import { act, openApp, screen, waitFor, within } from '../utils/render'
import { server } from '../utils/server'

describe('Home', () => {
  let observer: ReturnType<typeof installFakeIntersectionObserver> | undefined
  afterEach(() => { observer?.uninstall(); observer = undefined })

  it('shows the newest videos as cards, each a link to watch it', async () => {
    const { user, router } = openApp('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Home' })).toBeInTheDocument()
    const grid = await screen.findByRole('list', { name: 'Newest videos' })
    expect(within(grid).getAllByRole('listitem')).toHaveLength(24)
    const first = within(grid).getAllByRole('listitem')[0]
    expect(within(first).getByRole('link', { name: 'Building a bird box' })).toHaveAttribute('href', '/watch/wo000000000')
    expect(within(first).getByText('Saved')).toBeInTheDocument()
    expect(within(first).getByRole('link', { name: 'Workshop Notes' })).toHaveAttribute('href', '/channels/UCworkshop00000000000001')
    expect(within(first).getByText(/^1K views · \d+ \w+ ago$/)).toBeInTheDocument()
    expect(within(grid).getByText('Fetching')).toBeInTheDocument()
    await user.click(within(first).getByRole('link', { name: 'Building a bird box' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/watch/wo000000000'))
  })

  it('offers a chip per channel', async () => {
    const { user, router } = openApp('/')
    const chips = screen.getByRole('navigation', { name: 'Channels' })
    expect(within(chips).getByText('All')).toHaveAttribute('aria-current', 'page')
    await user.click(await within(chips).findByRole('link', { name: channels[1].title }))
    expect(router.state.location.pathname).toBe(`/channels/${channels[1].id}`)
  })

  it('reads more as the page scrolls, and offers Show more', async () => {
    server.use(videosLong)
    observer = installFakeIntersectionObserver()
    const { user } = openApp('/')
    const grid = await screen.findByRole('list', { name: 'Newest videos' })
    expect(within(grid).getAllByRole('listitem')).toHaveLength(24)
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(within(grid).getAllByRole('listitem')).toHaveLength(48))
    // The observer's first report is "out of view", which asks for nothing.
    const watched = [...observer.observers.at(-1)!.targets][0]
    act(() => { observer!.intersect(watched, false) })
    expect(within(grid).getAllByRole('listitem')).toHaveLength(48)
    act(() => { observer!.scrollToEnd() })
    await waitFor(() => expect(within(grid).getAllByRole('listitem')).toHaveLength(60))
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
  })

  it('draws placeholder cards while the next page arrives', async () => {
    server.use(videosLaterPageLoading)
    const { user } = openApp('/')
    await user.click(await screen.findByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull())
    expect(screen.getAllByRole('listitem')).toHaveLength(24)
  })

  it('says why a later page failed, with Try again', async () => {
    server.use(videosLaterPageError)
    const { user } = openApp('/')
    await user.click(await screen.findByRole('button', { name: 'Show more' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('(503)')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('draws a card without a channel picture, views or length', async () => {
    server.use(channelsLoading, videosFrom([{ id: 'xx000000000', channel_id: 'UCunknown', channel: null, title: 'Untitled', published: '2026-01-01T00:00:00Z', duration: null, thumbnail: null, views: null, cache_state: null, cache_bytes: null }]))
    openApp('/')
    const grid = await screen.findByRole('list', { name: 'Newest videos' })
    expect(within(grid).getByRole('link', { name: 'Channel' })).toBeInTheDocument()
    expect(within(grid).getByText(/^\d+ \w+ ago$/)).toBeInTheDocument()
  })

  it('before the first sync, says where to make one', async () => {
    server.use(videosNone)
    const { user, router } = openApp('/')
    expect(await screen.findByText('No videos yet')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Copy it from Admin' }))
    expect(router.state.location.pathname).toBe('/admin/system')
  })

  it('says the server could not answer, with Try again', async () => {
    server.use(videosError)
    openApp('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
