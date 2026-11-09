import { afterEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { installFakeIntersectionObserver } from 'strata-react/testing'
import { channels } from '../../src/mocks/fixtures'
import { channelsEmpty, channelsError, videosLaterPageError, videosLong } from '../../src/mocks/handlers'
import { act, openApp, screen, within } from '../utils/render'
import { server } from '../utils/server'

const workshop = channels.find(c => c.title === 'Workshop Notes')!
const coasts = channels.find(c => c.title === 'Rivers and Coasts')!

describe('Channels', () => {
  it('lists the channels by name, each a link to its videos', async () => {
    const { user, router } = openApp('/channels')
    expect(await screen.findByText(/^4\schannels with 24\svideos; the newest is from/)).toBeInTheDocument()
    const list = screen.getByRole('list', { name: 'Channels' })
    expect(within(list).getAllByRole('link').map(l => l.querySelector('.font-medium')?.textContent)).toEqual(['Kitchen Science', 'Night Sky', 'Rivers and Coasts', 'Workshop Notes'])
    expect(within(list).getAllByText('No picture')).toHaveLength(1)
    await user.click(within(list).getByRole('link', { name: /Workshop Notes/ }))
    expect(router.state.location.pathname).toBe(`/channels/${workshop.id}`)
  })

  it('says where channels come from when there are none', async () => {
    server.use(channelsEmpty)
    openApp('/channels')
    expect(await screen.findByText('No channels yet')).toBeInTheDocument()
  })

  it('leaves the date off a channel with no videos', async () => {
    server.use(http.get('*/api/channels', () => HttpResponse.json([{ ...coasts, videos: 0, latest: null }])))
    openApp('/channels')
    expect(await screen.findByText(/^0\svideos$/)).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(channelsError)
    openApp('/channels')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})

describe('A channel', () => {
  let observer: ReturnType<typeof installFakeIntersectionObserver> | undefined
  afterEach(() => { observer?.uninstall(); observer = undefined })

  it('lists its videos newest first, without repeating the channel on each', async () => {
    openApp(`/channels/${workshop.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Workshop Notes' })).toBeInTheDocument()
    expect(screen.getByText('@workshopnotes')).toBeInTheDocument()
    expect(screen.getByText(/^6\svideos, the newest from/)).toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Videos from Workshop Notes, newest first' })
    expect(within(list).getAllByRole('link')).toHaveLength(6)
    expect(within(list).queryByText(/Workshop Notes ·/)).toBeNull()
    expect(await screen.findByText('That is every video from Workshop Notes.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'All channels' })).toHaveAttribute('href', '/channels')
  })

  it('names a channel without a handle as a channel', async () => {
    openApp(`/channels/${coasts.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Rivers and Coasts' })).toBeInTheDocument()
    expect(screen.getByText('Channel')).toBeInTheDocument()
  })

  it('reads a long channel a page at a time, after the last video held', async () => {
    server.use(videosLong)
    observer = installFakeIntersectionObserver()
    const { user } = openApp(`/channels/${workshop.id}`)
    const list = await screen.findByRole('list', { name: /^Videos from Workshop Notes/ })
    expect(await within(list).findByRole('link', { name: /Episode 60/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show older videos' }))
    expect(await within(list).findByRole('link', { name: /Episode 36/ })).toBeInTheDocument()
    act(() => { observer!.scrollToEnd() })
    expect(await screen.findByText('That is every video from Workshop Notes.')).toBeInTheDocument()
  })

  it('offers Try again when a later page fails', async () => {
    server.use(videosLaterPageError)
    const { user } = openApp(`/channels/${workshop.id}`)
    await user.click(await screen.findByRole('button', { name: 'Show older videos' }))
    expect(await screen.findByRole('button', { name: /Try again/ })).toBeInTheDocument()
  })

  it('says when the library has none of its videos', async () => {
    server.use(http.get('*/api/videos', () => HttpResponse.json({ videos: [], has_more: false })))
    openApp(`/channels/${workshop.id}`)
    expect(await screen.findByText('No videos yet')).toBeInTheDocument()
  })

  it('says the server could not answer for the channel', async () => {
    server.use(http.get('*/api/channels/:id', () => new HttpResponse(null, { status: 503 })))
    openApp(`/channels/${workshop.id}`)
    expect(await screen.findByRole('alert')).toHaveTextContent('(503)')
  })

  it('says when the library no longer has the channel', async () => {
    openApp('/channels/UCgone')
    expect(await screen.findByRole('alert')).toHaveTextContent('The library has no such channel.')
  })
})
