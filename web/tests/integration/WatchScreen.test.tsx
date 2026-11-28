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
    // jsdom has neither MediaSource nor native HLS, so the player says so, with Try again.
    const failed = await screen.findByRole('alert')
    expect(failed).toHaveTextContent('Could not load this video')
    expect(failed).toHaveTextContent('This browser cannot play this kind of stream.')
    expect(within(failed).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(mock.plays).toEqual([id])
    await user.click(await screen.findByRole('link', { name: /Workshop Notes\s*6 videos/ }))
    expect(router.state.location.pathname).toBe('/channels/UCworkshop00000000000001')
  })

  it('names the video and its channel over the picture, the channel leading to its page', async () => {
    const { user, router } = openApp(`/watch/${id}`)
    const player = await screen.findByRole('group', { name: 'Building a bird box' })
    expect(within(player).getByText('Building a bird box')).toBeInTheDocument()
    const channel = within(player).getAllByRole('link', { name: 'Workshop Notes' })
    expect(channel).toHaveLength(2)                          // the picture and the name
    await user.click(channel[1])
    expect(router.state.location.pathname).toBe('/channels/UCworkshop00000000000001')
    expect(router.state.location.state).toEqual({ from: { source: 'watch', detail: id } })
  })

  it('names the channel over the picture by its first letter while the channel list is still coming', async () => {
    server.use(channelsLoading)
    openApp(`/watch/${id}`)
    const player = await screen.findByRole('group', { name: 'Building a bird box' })
    expect(within(player).getAllByRole('link', { name: 'Workshop Notes' })).toHaveLength(2)
    expect(within(player).getByText('W')).toBeInTheDocument()
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
    expect(await screen.findByText('Fetching: 0:12 of 4:00 so far', { selector: 'dd' }, { timeout: 3000 })).toBeInTheDocument()
    // The player says it is still being made, with the same progress.
    const player = screen.getByRole('group', { name: 'Building a bird box' })
    expect(within(player).getByText('Still being made')).toBeInTheDocument()
    expect(within(player).getByText('Fetching: 0:12 of 4:00 so far')).toBeInTheDocument()
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
    expect(within(await screen.findByRole('group', { name: 'Building a bird box' })).getAllByRole('link', { name: 'Workshop Notes' })).toHaveLength(2)
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

  it('says what was done to the sound, and plays at the server’s gain with Louder past 100%', async () => {
    openApp(`/watch/${id}`)
    expect(await screen.findByText(/^Lowered 3\.0\sdB to the usual level$/)).toBeInTheDocument()
    // jsdom has no Web Audio, so the player cannot go past 100% here and offers no Louder (strata-react's own tests cover it).
    expect(screen.queryByRole('button', { name: /Louder/ })).toBeNull()
  })

  it('keeps asking while the loudness of a whole copy is measured, and says so', async () => {
    mock.streams[id] = { ...streams.ready, loudness: { gain: null, measured: 0, integrated: null, peak: null, final: false } }
    openApp(`/watch/${id}`)
    expect(await screen.findByText('Being measured')).toBeInTheDocument()
    mock.streams[id] = streams.ready
    expect(await screen.findByText(/^Lowered 3\.0\sdB to the usual level$/, {}, { timeout: 3000 })).toBeInTheDocument()
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
  // jsdom's <video> neither loads nor plays: it is told its length, and played to a time, as Chrome would report them.
  const video = () => screen.getByLabelText('Building a bird box, video', { selector: 'video' }) as HTMLVideoElement
  const lasting = (d: number) => act(() => {
    Object.defineProperty(video(), 'readyState', { configurable: true, value: 1 })            // the metadata is in, so a seek goes straight to the element
    Object.defineProperty(video(), 'duration', { configurable: true, value: d }); video().dispatchEvent(new Event('durationchange'))
  })
  const playTo = (t: number) => act(() => {
    Object.defineProperty(video(), 'paused', { configurable: true, value: false })
    Object.defineProperty(video(), 'currentTime', { configurable: true, writable: true, value: t })
    video().dispatchEvent(new Event('play')); video().dispatchEvent(new Event('timeupdate'))
  })
  const span = (name: string | RegExp) => screen.findByRole('img', { name })
  const ready = async () => { await screen.findByRole('group', { name: 'Building a bird box' }); lasting(400) }

  it('draws the parts on the seek bar, asks for an intro and skips a sponsor read with Undo', async () => {
    const { user } = openApp(`/watch/${id}`)
    await ready()
    for (const name of ['Intro, 0:00 to 0:12', 'Sponsor, 1:00 to 1:35', 'Credits and end cards, 6:00 to 6:40']) expect(await span(name)).toBeInTheDocument()
    playTo(3)
    await user.click(screen.getByRole('button', { name: 'Skip intro' }))
    expect(video().currentTime).toBe(12)
    playTo(5)                                                                       // back in the intro: it was skipped once, so no button again
    expect(screen.queryByRole('button', { name: 'Skip intro' })).not.toBeInTheDocument()
    playTo(61)
    expect(video().currentTime).toBe(95)
    expect(screen.getByText('Skipped sponsor')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(video().currentTime).toBe(61)
    playTo(62)                                                                      // let play after Undo
    expect(video().currentTime).toBe(62)
  })

  it('places the parts by the library’s length while the copy is still being fetched', async () => {
    mock.streams[id] = streams.playable
    openApp(`/watch/${id}`)
    await screen.findByRole('group', { name: 'Building a bird box' })
    lasting(20)                                                                     // only the part fetched so far
    expect(await span('Sponsor, 1:00 to 1:35')).toHaveStyle({ left: '25%' })        // 1:00 of the video's 4:00
  })

  it('places the parts by what the element knows when the library has no length', async () => {
    server.use(http.get(`*/api/videos/${id}`, () => HttpResponse.json({ ...videos[0], duration: null, plays: 0, last_played: null })))
    openApp(`/watch/${id}`)
    await screen.findByRole('group', { name: 'Building a bird box' })
    lasting(120)
    expect(await span('Sponsor, 1:00 to 1:35')).toHaveStyle({ left: '50%' })
  })

  it('mutes a part whose action is mute, and unmutes after it', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'sponsor', start: 10, end: 20, action: 'mute' }], categories: kindsFor(mock.settings), error: null })))
    const { user } = openApp(`/watch/${id}`)
    await ready()
    await span('Sponsor, 0:10 to 0:20')
    playTo(11)
    expect(video().muted).toBe(true)
    expect(screen.getByText('Muted sponsor')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(video().muted).toBe(false)
    playTo(12); playTo(25)
    expect(video().muted).toBe(false)
  })

  it('unmutes once a muted part ends', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'sponsor', start: 10, end: 20, action: 'mute' }], categories: kindsFor(mock.settings), error: null })))
    openApp(`/watch/${id}`)
    await ready()
    await span(/Sponsor/)
    playTo(11)
    expect(video().muted).toBe(true)
    playTo(21)
    expect(video().muted).toBe(false)
  })

  it('counts a part it skips as seen', async () => {
    openApp(`/watch/${id}`)
    await ready()
    await span(/Sponsor/)
    playTo(61)
    expect(video().currentTime).toBe(95)
    act(() => { Object.defineProperty(video(), 'paused', { configurable: true, value: true }); video().dispatchEvent(new Event('pause')) })
    await waitFor(() => expect(mock.reports.at(-1)!.report.watched).toBe(35))      // the sponsor read's 35 seconds
  })

  it('plays on with nothing drawn when the segments cannot be read', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => new HttpResponse(null, { status: 503 })))
    openApp(`/watch/${id}`)
    expect(await screen.findByText(/^The parts to skip could not be read:/)).toBeInTheDocument()
    expect(screen.getByText('The video plays as it is.')).toBeInTheDocument()
    lasting(400)
    expect(screen.queryByRole('img', { name: /Sponsor/ })).not.toBeInTheDocument()
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: sampleSegments, categories: kindsFor(mock.settings), error: null })))
    await userEvent.click(within(screen.getByRole('group', { name: /could not be read/ })).getByRole('button', { name: 'Try again' }))
    expect(await span(/Sponsor/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/could not be read/)).not.toBeInTheDocument())
  })

  it('says when the server could not ask the source, and still draws what it had', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: sampleSegments, categories: kindsFor(mock.settings), error: 'SponsorBlock could not be reached: timed out.' })))
    openApp(`/watch/${id}`)
    expect(await screen.findByText('The parts to skip could not be looked up: SponsorBlock could not be reached: timed out.')).toBeInTheDocument()
    expect(screen.getByText('The video plays as it is.')).toBeInTheDocument()
    lasting(400)
    expect(await span(/Sponsor/)).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: /could not be looked up/ })).queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('skips an automatic part inside an Ask one', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'intro', start: 0, end: 30, action: 'skip' }, { category: 'sponsor', start: 10, end: 20, action: 'skip' }], categories: kindsFor(mock.settings), error: null })))
    openApp(`/watch/${id}`)
    await ready()
    await span('Intro, 0:00 to 0:10')
    playTo(5)
    expect(screen.getByRole('button', { name: 'Skip intro' })).toBeInTheDocument()
    playTo(11)
    expect(video().currentTime).toBe(20)
    playTo(21)
    expect(screen.getByRole('button', { name: 'Skip intro' })).toBeInTheDocument()
  })

  it('draws nothing for a kind that is off', async () => {
    server.use(http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments: [{ category: 'filler', start: 1, end: 2, action: 'skip' }], categories: kindsFor(mock.settings), error: null })))
    openApp(`/watch/${id}`)
    await ready()
    expect(screen.queryByRole('img', { name: /Filler/ })).not.toBeInTheDocument()
  })
})

describe('Watch a Plex film', () => {
  it('says what the browser decodes and streams the copy the server names', async () => {
    Object.defineProperty(navigator, 'mediaCapabilities', { configurable: true, value: { decodingInfo: async ({ video }: { video: { contentType: string; transferFunction?: string } }) => ({ supported: video.contentType.includes('hvc1'), smooth: !video.transferFunction, powerEfficient: true }) } })
    try {
      openApp('/watch/plex-101')
      expect(await screen.findByRole('heading', { level: 1, name: 'Harbour Lights' })).toBeInTheDocument()
      await waitFor(() => expect(mock.plays).toEqual(['plex-101']))
      expect(mock.decodes).toEqual([['h264', 'hevc']])                      // HDR not smooth here, so not claimed
    } finally { Reflect.deleteProperty(navigator, 'mediaCapabilities') }
  })

  it('sends nothing for a video from elsewhere', async () => {
    openApp(`/watch/${id}`)
    await waitFor(() => expect(mock.plays).toEqual([id]))
    expect(mock.decodes).toEqual([null])
  })
})
