import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { episodes, streams, videos } from '../../src/mocks/fixtures'
import { channelsLoading, playFails, playLoading, shuffleError, videoLoading, withProgramme } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

const id = 'wo000000000'

describe('Watch', () => {
  it('records the play and plays a saved copy at once', async () => {
    const { user, router } = openApp(`/watch/${id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Building a bird box' })).toBeInTheDocument()
    expect(await screen.findByText('Saved on this server')).toBeInTheDocument()
    expect(screen.getByText('1080p VP9 + AAC')).toBeInTheDocument()
    expect(screen.getByText(/^1K views · \d+ \w+ ago$/, { selector: 'dd' })).toBeInTheDocument()
    // jsdom has neither MediaSource nor native HLS, so the player says what it needs.
    expect(await screen.findByRole('alert')).toHaveTextContent('This browser cannot play the stream.')
    expect(mock.plays).toEqual([id])
    await user.click(await screen.findByRole('link', { name: /Workshop Notes\s*6 videos/ }))
    expect(router.state.location.pathname).toBe('/channels/UCworkshop00000000000001')
  })

  it('offers other videos up next, not this one', async () => {
    const { user, router } = openApp(`/watch/${id}`)
    const next = await screen.findByRole('list', { name: 'Up next' })
    const links = within(next).getAllByRole('link')
    expect(links.length).toBeGreaterThan(0)
    expect(links.map(l => l.getAttribute('href'))).not.toContain(`/watch/${id}`)
    await user.click(links[0])
    await waitFor(() => expect(router.state.location.pathname).not.toBe(`/watch/${id}`))
  })

  it('says why Up next is missing', async () => {
    server.use(shuffleError)
    openApp(`/watch/${id}`)
    const section = await screen.findByRole('region', { name: 'Up next' })
    expect(await within(section).findByRole('alert')).toHaveTextContent('(503)')
  })

  it('says what it is waiting for while the first seconds arrive', async () => {
    mock.streams[id] = streams.fetching
    openApp(`/watch/${id}`)
    expect(await screen.findByText('Fetching 1080p AV1 + AAC. It starts in a moment.')).toBeInTheDocument()
    mock.streams[id] = streams.playable
    expect(await screen.findByText('Fetching: 0:12 of 4:00 so far', {}, { timeout: 3000 })).toBeInTheDocument()
  })

  it('says before a fetch starts that the quality is chosen then', async () => {
    mock.streams[id] = { ...streams.none, state: 'fetching' }
    openApp(`/watch/${id}`)
    expect(await screen.findByText('Chosen when the fetch starts')).toBeInTheDocument()
    expect(screen.getByText('Finding the best copy to fetch…')).toBeInTheDocument()
  })

  it('says why a fetch failed, and fetches again', async () => {
    mock.streams[id] = streams.failed
    const { user } = openApp(`/watch/${id}`)
    expect(await screen.findByText('This video could not be fetched')).toBeInTheDocument()
    expect(screen.getByText('Video unavailable. This video is private.')).toBeInTheDocument()
    expect(screen.getByText('Not saved')).toBeInTheDocument()
    mock.streams[id] = streams.ready
    await user.click(screen.getByRole('button', { name: 'Fetch again' }))
    expect(await screen.findByText('Saved on this server')).toBeInTheDocument()
    await waitFor(() => expect(mock.plays).toEqual([id, id]))
  })

  it('says it is asking while a second fetch starts', async () => {
    mock.streams[id] = streams.failed
    const { user } = openApp(`/watch/${id}`)
    const again = await screen.findByRole('button', { name: 'Fetch again' })
    server.use(playLoading)
    await user.click(again)
    expect(await screen.findByText('Asking for the video…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Fetch again' })).toBeNull()
  })

  it('names the channel from the channel list when the video does not', async () => {
    server.use(http.get(`*/api/videos/${id}`, () => HttpResponse.json({ ...videos[0], channel: null, plays: 0, last_played: null })))
    openApp(`/watch/${id}`)
    expect(await screen.findByRole('link', { name: /^Workshop Notes\s*6 videos$/ })).toBeInTheDocument()
  })

  it('says the fetch stopped when it gave no reason', async () => {
    mock.streams[id] = { ...streams.failed, error: null }
    openApp(`/watch/${id}`)
    expect(await screen.findByText('The fetch stopped without saying why.')).toBeInTheDocument()
  })

  it('says why the server would not start the fetch', async () => {
    server.use(playFails)
    openApp(`/watch/${id}`)
    expect(await screen.findByText('This video cannot start now')).toBeInTheDocument()
    expect(screen.getByText('3 videos are already being fetched; try again when one finishes.')).toBeInTheDocument()
  })

  it('counts plays here in words', async () => {
    mock.streams[id] = { ...streams.ready, plays: 1 }
    openApp(`/watch/${id}`)
    expect(await screen.findByText('once')).toBeInTheDocument()
  })

  it('says when the library has no such video', async () => {
    openApp('/watch/zzzzzzzzzzz')
    expect(await screen.findByText(/The library has no such video\./)).toBeInTheDocument()
  })

  it('shows the frame’s shape while the video is read', () => {
    server.use(videoLoading)
    openApp(`/watch/${id}`)
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  })

  it('names a video without a channel name as from a channel', async () => {
    server.use(channelsLoading, http.get(`*/api/videos/${id}`, () => HttpResponse.json({ ...videos[0], channel: null, plays: 0, last_played: null })))
    openApp(`/watch/${id}`)
    expect(await screen.findByRole('link', { name: 'Channel' })).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(http.get(`*/api/videos/${id}`, () => new HttpResponse(null, { status: 503 })))
    openApp(`/watch/${id}`)
    expect(await screen.findByText(/\(503\)/)).toBeInTheDocument()
  })
})

describe('Watch an iPlayer episode', () => {
  const e = episodes[0]

  it('says how long iPlayer offers it, with the programme in episodes', async () => {
    server.use(...withProgramme)
    openApp(`/watch/${e.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Chapter 3' })).toBeInTheDocument()
    expect(screen.getByText('Until 1 Jan 2099')).toBeInTheDocument()
    expect(screen.getByText(/^S2 E3 · /, { selector: 'dd' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /Harbour Lights\s*6 episodes/ })).toBeInTheDocument()
  })

  it('says when iPlayer no longer offers it', async () => {
    server.use(http.get(`*/api/videos/${e.id}`, () => HttpResponse.json({ ...e, gone: '2026-11-01T00:00:00Z', plays: 0, last_played: null })), ...withProgramme)
    openApp(`/watch/${e.id}`)
    expect(await screen.findByText(/^No longer offered/)).toBeInTheDocument()
    expect(screen.queryByText('On YouTube')).not.toBeInTheDocument()
  })
})
