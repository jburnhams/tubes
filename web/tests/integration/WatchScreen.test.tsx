import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { streams, videos } from '../../src/mocks/fixtures'
import { playFails, videoLoading } from '../../src/mocks/handlers'
import { openApp, screen, waitFor } from '../utils/render'
import { mock, server } from '../utils/server'

const id = 'wo000000000'

describe('Watch', () => {
  it('records the play and plays a saved copy at once', async () => {
    const { user, router } = openApp(`/watch/${id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Building a bird box' })).toBeInTheDocument()
    expect(await screen.findByText('All of it, kept in the cache')).toBeInTheDocument()
    expect(screen.getByText('Saved')).toBeInTheDocument()
    expect(screen.getByText('1080p VP9 + AAC')).toBeInTheDocument()
    // jsdom has neither MediaSource nor native HLS, so the player says what it needs.
    expect(await screen.findByRole('alert')).toHaveTextContent('This browser cannot play the stream.')
    expect(mock.plays).toEqual([id])
    await user.click(screen.getByRole('link', { name: 'Workshop Notes' }))
    expect(router.state.location.pathname).toBe('/channels/UCworkshop00000000000001')
  })

  it('says what it is waiting for while the first seconds arrive', async () => {
    mock.streams[id] = streams.fetching
    openApp(`/watch/${id}`)
    expect(await screen.findByRole('status')).toHaveTextContent('Fetching 1080p AV1 + AAC. It starts in a moment.')
    expect(screen.getByText('Fetching')).toBeInTheDocument()
    mock.streams[id] = streams.playable
    expect(await screen.findByText('0:12 of 4:00 so far', {}, { timeout: 3000 })).toBeInTheDocument()
  })

  it('says before a fetch starts that the quality is chosen then', async () => {
    mock.streams[id] = { ...streams.none, state: 'fetching' }
    openApp(`/watch/${id}`)
    expect(await screen.findByText('Chosen when the fetch starts')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Finding the best copy to fetch…')
  })

  it('says why a fetch failed, and fetches again', async () => {
    mock.streams[id] = streams.failed
    const { user } = openApp(`/watch/${id}`)
    expect(await screen.findByText('This video could not be fetched')).toBeInTheDocument()
    expect(screen.getByText('Video unavailable. This video is private.')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    mock.streams[id] = streams.ready
    await user.click(screen.getByRole('button', { name: 'Fetch again' }))
    expect(await screen.findByText('All of it, kept in the cache')).toBeInTheDocument()
    await waitFor(() => expect(mock.plays).toEqual([id, id]))
  })

  it('says the fetch stopped when it gave no reason', async () => {
    mock.streams[id] = { ...streams.failed, error: null }
    openApp(`/watch/${id}`)
    expect(await screen.findByText('The fetch stopped without saying why.')).toBeInTheDocument()
  })

  it('says why the server would not start the fetch', async () => {
    server.use(playFails)
    openApp(`/watch/${id}`)
    expect(await screen.findByRole('alert')).toHaveTextContent('3 videos are already being fetched; try again when one finishes.')
  })

  it('says when the library has no such video', async () => {
    openApp('/watch/zzzzzzzzzzz')
    expect(await screen.findByRole('alert')).toHaveTextContent('The library has no such video.')
  })

  it('shows the frame’s shape while the video is read', () => {
    server.use(videoLoading)
    openApp(`/watch/${id}`)
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  })

  it('names a video without a channel name as from a channel', async () => {
    server.use(http.get('*/api/videos/:id', () => HttpResponse.json({ ...videos[0], channel: null, plays: 0, last_played: null })))
    openApp(`/watch/${id}`)
    expect(await screen.findByRole('link', { name: 'Channel' })).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(http.get('*/api/videos/:id', () => new HttpResponse(null, { status: 503 })))
    openApp(`/watch/${id}`)
    expect(await screen.findByRole('alert')).toHaveTextContent('(503)')
  })
})
