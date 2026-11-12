// What is kept of each play and channel visit (src/tubes/viewing.py), and what comes of it: Continue
// watching on Home, part-watched videos first in Up next, and a play that picks up where the last stopped.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { channels, unfinished, videos } from '../../src/mocks/fixtures'
import { continueError, continuing } from '../../src/mocks/handlers'
import { act, openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

const id = 'wo000000000'

afterEach(() => { vi.useRealTimers(); Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }) })

describe('Continue watching', () => {
  it('is not on Home until something is part watched', async () => {
    openApp('/')
    await screen.findByRole('list', { name: 'Newest videos' })
    expect(screen.queryByRole('heading', { name: 'Continue watching' })).not.toBeInTheDocument()
  })

  it('leads Home with the part-watched videos, each saying how far it got, and a play from it says so', async () => {
    server.use(continuing)
    const { user, router } = openApp('/')
    const row = await screen.findByRole('list', { name: 'Continue watching' })
    const links = within(row).getAllByRole('link', { name: /watched$/ })
    expect(links.map(l => l.getAttribute('href'))).toEqual(unfinished.map(v => `/watch/${v.id}`))
    expect(links[0]).toHaveAccessibleName(`${unfinished[0].title}, 62% watched`)
    await user.click(links[1])
    await waitFor(() => expect(router.state.location.pathname).toBe(`/watch/${unfinished[1].id}`))
    await waitFor(() => expect(mock.playsFrom).toEqual([{ source: 'continue', rank: 1 }]))
  })

  it('says why it could not be read', async () => {
    server.use(continueError)
    openApp('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('(503)')
  })
})

describe('Where a play was started from', () => {
  it('is the home grid and the place in it', async () => {
    const { user } = openApp('/')
    const grid = await screen.findByRole('list', { name: 'Newest videos' })
    const second = within(grid).getAllByRole('listitem')[1]
    await user.click(within(second).getAllByRole('link')[0])
    await waitFor(() => expect(mock.playsFrom).toEqual([{ source: 'home', rank: 1 }]))
  })

  it('is the search and its words', async () => {
    const { user } = openApp('/search?q=moon')
    const results = await screen.findByRole('list', { name: 'Videos matching “moon”' })
    await user.click(within(results).getAllByRole('link')[0])
    await waitFor(() => expect(mock.playsFrom).toEqual([{ source: 'search', detail: 'moon', rank: 0 }]))
  })

  it('is the channel page and which channel', async () => {
    const { user } = openApp(`/channels/${channels[0].id}`)
    const grid = await screen.findByRole('list', { name: `Videos from ${channels[0].title}` })
    await user.click(within(grid).getAllByRole('link')[0])
    await waitFor(() => expect(mock.playsFrom).toEqual([{ source: 'channel', detail: channels[0].id, rank: 0 }]))
  })

  it('is Up next and the video it was beside; the part-watched come first there', async () => {
    server.use(continuing)
    const { user } = openApp(`/watch/${unfinished[0].id}`)
    const next = await screen.findByRole('list', { name: 'Up next' })
    await waitFor(() => expect(within(next).getAllByRole('link')[0]).toHaveAttribute('href', `/watch/${unfinished[1].id}`))
    const hrefs = within(next).getAllByRole('link').map(l => l.getAttribute('href'))
    expect(hrefs.slice(0, 2)).toEqual([`/watch/${unfinished[1].id}`, `/watch/${unfinished[2].id}`])
    expect(hrefs).not.toContain(`/watch/${unfinished[0].id}`)
    expect(new Set(hrefs).size).toBe(hrefs.length)                          // each once, though the shuffle has them too
    await user.click(within(next).getAllByRole('link')[0])
    await waitFor(() => expect(mock.playsFrom).toEqual([null, { source: 'up_next', detail: unfinished[0].id, rank: 0 }]))
  })

  it('is nothing for an address typed or shared', async () => {
    openApp(`/watch/${id}`)
    await waitFor(() => expect(mock.plays).toEqual([id]))
    expect(mock.playsFrom).toEqual([null])
  })
})

describe('Channel visits', () => {
  it('are kept with where they came from: the Channels page, the watch page, the rail', async () => {
    const { user, router } = openApp('/channels')
    await user.click(within(await screen.findByRole('list', { name: 'Channels' })).getAllByRole('link')[1])
    await waitFor(() => expect(mock.channelViews).toEqual([{ id: channels[1].id, from: { source: 'channels', rank: 1 } }]))
    await router.navigate(`/watch/${id}`)
    await user.click(await screen.findByRole('link', { name: /Workshop Notes\s*6 videos/ }))
    await waitFor(() => expect(mock.channelViews.at(-1)).toEqual({ id: 'UCworkshop00000000000001', from: { source: 'watch', detail: id } }))
    await user.click(within(screen.getByRole('list', { name: 'Videos from Workshop Notes' })).getAllByRole('link')[0])
    await screen.findByRole('list', { name: 'Up next' })
    await user.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: channels[1].title }))
    await waitFor(() => expect(mock.channelViews.at(-1)).toEqual({ id: channels[1].id, from: { source: 'rail', rank: 1 } }))
  })

  it('count a typed address as one visit, and a second visit again', async () => {
    const { router } = openApp(`/channels/${channels[0].id}`)
    await waitFor(() => expect(mock.channelViews).toEqual([{ id: channels[0].id, from: null }]))
    await router.navigate('/')
    await router.navigate(`/channels/${channels[0].id}`)
    await waitFor(() => expect(mock.channelViews).toHaveLength(2))
  })
})

describe('A play', () => {
  it('reports how it went as the page is left, and Home then offers it to continue', async () => {
    const { router } = openApp(`/watch/${id}`)
    const video = drive((await screen.findByLabelText('Building a bird box', { selector: 'video' })) as HTMLVideoElement)
    await video.play(50)
    mock.unfinished = [{ ...videos[0], resume: 50, progress: 0.0833 }]                          // what the server makes of the report
    await router.navigate('/')
    await waitFor(() => expect(mock.reports).toEqual([{ play: 1, report: { position: 50, watched: 50, length: 600 } }]))
    expect(await screen.findByRole('link', { name: 'Building a bird box, 8% watched' })).toBeInTheDocument()
  })

  it('says nothing when nothing was seen', async () => {
    const { router } = openApp(`/watch/${id}`)
    await screen.findByText('Saved on this server')
    await router.navigate('/')
    await screen.findByRole('list', { name: 'Newest videos' })
    expect(mock.reports).toEqual([])
  })

  it('picks up where the last one stopped, with Start over', async () => {
    mock.resume[id] = 125
    const { user } = openApp(`/watch/${id}`)
    const status = await screen.findByText(/^Picked up at 2:05/)
    await user.click(within(status).getByRole('button', { name: 'Start over' }))
    expect(screen.queryByText(/^Picked up at/)).not.toBeInTheDocument()
  })

  it('says so for a few seconds only', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mock.resume[id] = 125
    openApp(`/watch/${id}`)
    await screen.findByText(/^Picked up at 2:05/)
    await act(() => { vi.advanceTimersByTime(8000) })
    expect(screen.queryByText(/^Picked up at/)).not.toBeInTheDocument()
  })
})

/** jsdom's <video> neither plays nor moves: this one is driven by hand, as Chrome would report a play. */
function drive(video: HTMLVideoElement) {
  const state = { t: 0, paused: true, seeking: false, duration: 600 }
  Object.defineProperty(video, 'currentTime', { configurable: true, get: () => state.t, set: (t: number) => { state.t = t } })
  Object.defineProperty(video, 'paused', { configurable: true, get: () => state.paused })
  Object.defineProperty(video, 'seeking', { configurable: true, get: () => state.seeking })
  Object.defineProperty(video, 'duration', { configurable: true, get: () => state.duration })
  const fire = (type: string) => act(() => { video.dispatchEvent(new Event(type)) })
  return {
    state, fire,
    /** Play from where it is to `to`, a time update every quarter second. */
    play: (to: number) => act(() => { state.paused = false; for (let t = state.t; t <= to; t += 0.25) { state.t = t; video.dispatchEvent(new Event('timeupdate')) } }),
    seek: (to: number) => act(() => { state.seeking = true; state.t = to; video.dispatchEvent(new Event('seeking')); video.dispatchEvent(new Event('timeupdate')); state.seeking = false }),
  }
}

describe('The player', () => {

  it('reports the seconds seen as it plays, pauses, is hidden and ends', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    openApp(`/watch/${id}`)
    const video = drive((await screen.findByLabelText('Building a bird box', { selector: 'video' })) as HTMLVideoElement)
    await waitFor(() => expect(mock.plays).toHaveLength(1))
    await video.play(30)
    await act(() => { vi.advanceTimersByTime(15_000) })                                     // every 15 seconds while it plays
    await waitFor(() => expect(mock.reports).toEqual([{ play: 1, report: { position: 30, watched: 30, length: 600 } }]))
    await video.seek(10); await video.play(20)                                              // back over a part: counted once
    await video.seek(300)                                                                   // a jump forward counts nothing
    video.state.paused = true; await video.fire('pause')
    await waitFor(() => expect(mock.reports.at(-1)).toEqual({ play: 1, report: { position: 300, watched: 30, length: 600 } }))
    await act(() => { vi.advanceTimersByTime(15_000) })                                     // paused: no report
    await video.fire('pause')                                                               // nothing new: none either
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    await video.play(310)
    await act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    await waitFor(() => expect(mock.reports.at(-1)!.report.watched).toBe(40))
    await act(() => { window.dispatchEvent(new Event('pagehide')) })                         // nothing new since
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    await act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    await video.seek(598.5); await video.play(599.75)
    video.state.t = 600; await video.fire('ended')
    await waitFor(() => expect(mock.reports.at(-1)!.report).toEqual({ position: 600, watched: 42, length: 600 }))
    expect(mock.reports).toHaveLength(4)                                                    // 15 s, pause, hidden, end
  })

  it('counts a part it skips as seen', async () => {
    const { user } = openApp(`/watch/${id}`)
    const video = drive((await screen.findByLabelText('Building a bird box', { selector: 'video' })) as HTMLVideoElement)
    await screen.findByRole('img', { name: /Parts that can be skipped/ })
    await video.play(60.5)                                                                  // into the sponsor read (1:00-1:35), skipped as it starts
    await waitFor(() => expect(video.state.t).toBe(95))
    video.state.paused = true; await video.fire('pause')
    await waitFor(() => expect(mock.reports.at(-1)!.report.watched).toBe(95))
    await video.seek(5)
    await user.click(screen.getByRole('button', { name: 'Skip intro ›' }))                  // one the person skips counts too, though seen already here
    await waitFor(() => expect(video.state.t).toBe(12))
  })

  it('keeps playing when a report cannot be sent', async () => {
    server.use(http.post('*/api/plays/:id', () => new HttpResponse(null, { status: 503 })))
    openApp(`/watch/${id}`)
    const video = drive((await screen.findByLabelText('Building a bird box', { selector: 'video' })) as HTMLVideoElement)
    await video.play(5); video.state.paused = true; await video.fire('pause')
    expect(screen.queryByText(/could not/)).not.toBeInTheDocument()
  })
})
