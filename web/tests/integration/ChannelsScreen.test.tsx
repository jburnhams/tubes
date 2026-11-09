import { afterEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { installFakeIntersectionObserver } from 'strata-react/testing'
import { channels } from '../../src/mocks/fixtures'
import { channelsEmpty, channelsError, videosLaterPageError, videosLong, videosNone } from '../../src/mocks/handlers'
import { act, openApp, screen, waitFor, within } from '../utils/render'
import { server } from '../utils/server'

const workshop = channels.find(c => c.title === 'Workshop Notes')!
const coasts = channels.find(c => c.title === 'Rivers and Coasts')!

describe('Channels', () => {
  it('shows every channel with its picture and count, each a link to its page', async () => {
    const { user, router } = openApp('/channels')
    const list = await screen.findByRole('list', { name: 'Channels' })
    expect(within(list).getAllByRole('link').map(l => l.querySelector('span:not([aria-hidden]) > span')?.textContent)).toEqual(['Kitchen Science', 'Night Sky', 'Rivers and Coasts', 'Workshop Notes'])
    expect(within(list).getAllByText('6 videos')).toHaveLength(4)
    await user.click(within(list).getByRole('link', { name: /Workshop Notes/ }))
    expect(router.state.location.pathname).toBe(`/channels/${workshop.id}`)
  })

  it('counts one video as one', async () => {
    server.use(http.get('*/api/channels', () => HttpResponse.json([{ ...coasts, videos: 1 }])))
    openApp('/channels')
    expect(await screen.findByText('1 video')).toBeInTheDocument()
  })

  it('says where channels come from when there are none', async () => {
    server.use(channelsEmpty)
    openApp('/channels')
    expect(await screen.findByText('No channels yet')).toBeInTheDocument()
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

  it('shows its name, handle and count over its videos, without repeating the channel on each', async () => {
    openApp(`/channels/${workshop.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Workshop Notes' })).toBeInTheDocument()
    expect(screen.getByText('@workshopnotes · 6 videos')).toBeInTheDocument()
    const grid = await screen.findByRole('list', { name: 'Videos from Workshop Notes' })
    expect(within(grid).getAllByRole('listitem')).toHaveLength(6)
    expect(within(grid).queryByRole('link', { name: 'Workshop Notes' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
  })

  it('leaves out a handle it does not have, and counts one video as one', async () => {
    server.use(http.get('*/api/channels/:id', () => HttpResponse.json({ ...coasts, videos: 1 })))
    openApp(`/channels/${coasts.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Rivers and Coasts' })).toBeInTheDocument()
    expect(screen.getByText('1 video')).toBeInTheDocument()
  })

  it('reads a long channel a page at a time, after the last video held', async () => {
    server.use(videosLong)
    observer = installFakeIntersectionObserver()
    const { user } = openApp(`/channels/${workshop.id}`)
    const grid = await screen.findByRole('list', { name: 'Videos from Workshop Notes' })
    expect(within(grid).getByRole('link', { name: 'Episode 60' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    expect(await within(grid).findByRole('link', { name: 'Episode 36' })).toBeInTheDocument()
    act(() => { observer!.scrollToEnd() })
    expect(await within(grid).findByRole('link', { name: 'Episode 1' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull())
  })

  it('offers Try again when a later page fails', async () => {
    server.use(videosLaterPageError)
    observer = installFakeIntersectionObserver()
    const { user } = openApp(`/channels/${workshop.id}`)
    await user.click(await screen.findByRole('button', { name: 'Show more' }))
    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('says when the library has none of its videos', async () => {
    server.use(videosNone)
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
