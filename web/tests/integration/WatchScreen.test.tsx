import { describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import userEvent from '@testing-library/user-event'
import { episodes, kindsFor, sampleSegments, streams, videos } from '../../src/mocks/fixtures'
import { channelsLoading, playFails, playLoading, shuffleError, videoLoading, withProgramme } from '../../src/mocks/handlers'
import { act, openApp, screen, waitFor, within } from '../utils/render'
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

describe('Skipping parts of a video', () => {
  const video = () => screen.getByLabelText('Building a bird box', { selector: 'video' }) as HTMLVideoElement
  const playTo = (t: number) => act(() => { Object.defineProperty(video(), 'currentTime', { configurable: true, writable: true, value: t }); video().dispatchEvent(new Event('timeupdate')) })

  it('draws the parts on a timeline, asks for an intro and skips a sponsor read with Undo', async () => {
    const { user } = openApp(`/watch/${id}`)
    expect(await screen.findByRole('img', { name: /^Parts that can be skipped: Intro 0:00–0:12, Sponsor 1:00–1:35, Credits and end cards 6:00–6:40$/ })).toBeInTheDocument()
    playTo(3)
    await user.click(screen.getByRole('button', { name: 'Skip intro ›' }))
    expect(video().currentTime).toBe(12)
    playTo(5)                                                                       // back in the intro: it was skipped once, so no button again
    expect(screen.queryByRole('button', { name: 'Skip intro ›' })).not.toBeInTheDocument()
    playTo(61)
    expect(video().currentTime).toBe(95)
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent('Skipped sponsor')
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(video().currentTime).toBe(60)
    playTo(62)                                                                      // let play after Undo
    expect(video().currentTime).toBe(62)
  })

  it('mutes a part whose action is mute, and unmutes after it', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'sponsor', start: 10, end: 20, action: 'mute' }], categories: kindsFor(mock.settings), error: null })))
    const { user } = openApp(`/watch/${id}`)
    await screen.findByRole('img', { name: /Sponsor 0:10–0:20/ })
    playTo(11)
    expect(video().muted).toBe(true)
    expect(screen.getByText('Muted sponsor')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(video().muted).toBe(false)
    playTo(12); playTo(25)
    expect(video().muted).toBe(false)
  })

  it('unmutes once a muted part ends, and the notice goes after a while', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'sponsor', start: 10, end: 20, action: 'mute' }], categories: kindsFor(mock.settings), error: null })))
      openApp(`/watch/${id}`)
      await screen.findByRole('img', { name: /Sponsor/ })
      playTo(11)
      expect(video().muted).toBe(true)
      act(() => { Object.defineProperty(video(), 'duration', { configurable: true, value: 40 }); video().dispatchEvent(new Event('durationchange')) })
      expect(screen.getByRole('img', { name: /Sponsor/ }).firstElementChild).toHaveStyle({ left: '25%' })     // placed by the picture's own length
      act(() => { Object.defineProperty(video(), 'duration', { configurable: true, value: NaN }); video().dispatchEvent(new Event('durationchange')) })
      playTo(21)
      expect(video().muted).toBe(false)
      act(() => { vi.advanceTimersByTime(6000) })
      expect(screen.queryByText('Muted sponsor')).not.toBeInTheDocument()
    } finally { vi.useRealTimers() }
  })

  it('plays on with nothing drawn when the segments cannot be read', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => new HttpResponse(null, { status: 503 })))
    openApp(`/watch/${id}`)
    expect(await screen.findByText(/^The parts to skip could not be read: .* The video plays as it is\.$/)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /Parts that can be skipped/ })).not.toBeInTheDocument()
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: sampleSegments, categories: kindsFor(mock.settings), error: null })))
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('img', { name: /Parts that can be skipped/ })).toBeInTheDocument()
    expect(screen.queryByText(/could not be read/)).not.toBeInTheDocument()
  })

  it('says when the server could not ask the source, and still draws what it had', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: sampleSegments, categories: kindsFor(mock.settings), error: 'SponsorBlock could not be reached: timed out.' })))
    openApp(`/watch/${id}`)
    expect(await screen.findByText('The parts to skip could not be looked up: SponsorBlock could not be reached: timed out. The video plays as it is.')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Parts that can be skipped/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('skips an automatic part inside an Ask one', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'intro', start: 0, end: 30, action: 'skip' }, { category: 'sponsor', start: 10, end: 20, action: 'skip' }], categories: kindsFor(mock.settings), error: null })))
    openApp(`/watch/${id}`)
    await screen.findByRole('img', { name: /Intro 0:00–0:30/ })
    playTo(5)
    expect(screen.getByRole('button', { name: 'Skip intro ›' })).toBeInTheDocument()
    playTo(11)
    expect(video().currentTime).toBe(20)
    playTo(21)
    expect(screen.getByRole('button', { name: 'Skip intro ›' })).toBeInTheDocument()
  })

  it('draws nothing when there is nothing to skip, or the length is not known', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'filler', start: 1, end: 2, action: 'skip' }], categories: kindsFor(mock.settings), error: null })))
    openApp(`/watch/${id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Building a bird box' })).toBeInTheDocument()
    await screen.findByRole('alert')
    expect(screen.queryByRole('img', { name: /Parts that can be skipped/ })).not.toBeInTheDocument()
  })
})
