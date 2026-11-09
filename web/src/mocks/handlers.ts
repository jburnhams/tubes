// The mock server: MSW handlers for every endpoint the app calls, answering like a healthy server.
// One set serves the jsdom tests (Node, tests/utils/server.ts), Storybook (a service worker,
// .storybook/preview.tsx) and the visual suite (Node, strata-visual.config.ts), so the app's real
// fetch, query and DataView code runs in all three and nothing is a module mock.
//
// The named handlers below each replace one route to put a test, story or screenshot into another
// state: `server.use(videosError)` in a test, `msw.use(videosError)` in a story's beforeEach,
// `states: { error: [videosError] }` in the visual config.
import { delay, http, HttpResponse } from 'msw'
import { cursorOf, paths, type CacheItem, type Settings, type Stream, type Video, type VideoPage } from '../api'
import { cacheItems, channels, defaultSettings, library, longChannel, report, streams, systemStatus, systemTrouble, videos } from './fixtures'

/** What the mock server holds. Writes change it, so a test can pin a copy and see it pinned. */
export const mock = {
  settings: { ...defaultSettings } as Settings,
  items: [...cacheItems] as CacheItem[],
  plays: [] as string[],
  /** What /stream answers, by video id; anything else answers `ready`. */
  streams: {} as Record<string, Stream>,
  synced: library.synced,
}

/** Back to the healthy state: call between tests and stories. */
export function resetMock() {
  mock.settings = { ...defaultSettings }
  mock.items = [...cacheItems]
  mock.plays = []
  mock.streams = {}
  mock.synced = library.synced
}

// Matched as paths, so they answer whatever origin and base the app runs under.
const at = (path: string) => `*${path}`
const down = () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' })
const refused = (detail: string, status = 400) => HttpResponse.json({ detail }, { status })

/** Serves `GET /api/videos?channel=&q=&after=&limit=` from a list, as library.videos does: newest first, words in any order, after a cursor. */
export function videoPage(url: string, list: Video[]): VideoPage {
  const p = new URL(url).searchParams
  const words = (p.get('q') ?? '').toLowerCase().split(/\s+/).filter(Boolean)
  const after = p.get('after')
  const limit = Number(p.get('limit') ?? 24)
  const rest = list
    .filter(v => !p.get('channel') || v.channel_id === p.get('channel'))
    .filter(v => words.every(w => v.title.toLowerCase().includes(w)))
    .filter(v => !after || cursorOf(v) < after)
  return { videos: rest.slice(0, limit), has_more: rest.length > limit }
}

const find = (id: string) => videos.find(v => v.id === id) ?? longChannel.find(v => v.id === id)
const stream = (id: string) => mock.streams[id] ?? streams.ready

export const handlers = [
  http.get(at(paths.health), () => HttpResponse.json({ ok: true, version: systemStatus.version })),
  http.get(at(paths.system), () => HttpResponse.json({ ...systemStatus, cache_dir: mock.settings.cache_dir, library: { ...library, synced: mock.synced } })),
  http.get(at(paths.settings), () => HttpResponse.json(mock.settings)),
  http.put(at(paths.settings), async ({ request }) => {
    const body = (await request.json()) as Partial<Settings>
    for (const k of ['data_dir', 'cache_dir'] as const) if (body[k] !== undefined && !/^[/~]/.test(body[k])) return refused(`${k} must be an absolute path`)
    mock.settings = { ...mock.settings, ...body }
    return HttpResponse.json(mock.settings)
  }),
  http.post(at(paths.sync), () => {
    mock.synced = '2026-11-09T09:30:00+00:00'
    return HttpResponse.json({ channels: library.channels, videos: library.videos, synced: mock.synced })
  }),
  http.get(at(paths.channels), () => HttpResponse.json(channels)),
  http.get(at('/api/channels/:id'), ({ params }) => {
    const c = channels.find(c => c.id === params.id)
    return c ? HttpResponse.json(c) : refused(`There is no channel ${params.id} in the library.`, 404)
  }),
  http.get(at(paths.shuffle), ({ request }) => HttpResponse.json(videos.slice(0, Number(new URL(request.url).searchParams.get('count') ?? 24)))),
  http.get(at(paths.videos), ({ request }) => HttpResponse.json(videoPage(request.url, videos))),
  http.get(at('/api/videos/:id'), ({ params }) => {
    const v = find(String(params.id))
    const plays = mock.plays.filter(p => p === params.id).length
    return v ? HttpResponse.json({ ...v, plays, last_played: plays ? '2026-11-09T09:30:00+00:00' : null }) : refused(`There is no video ${params.id} in the library.`, 404)
  }),
  http.post(at('/api/videos/:id/play'), ({ params }) => {
    const id = String(params.id)
    if (!find(id)) return refused(`There is no video ${id} in the library.`, 404)
    mock.plays.push(id)
    return HttpResponse.json(stream(id))
  }),
  http.get(at('/api/videos/:id/stream'), ({ params }) => HttpResponse.json(stream(String(params.id)))),
  // The player's own requests. jsdom cannot play media, so these only need to answer; the visual suite never shoots a playing video.
  http.get(at('/api/media/:id/:name'), () => new HttpResponse('#EXTM3U\n#EXT-X-ENDLIST\n', { headers: { 'Content-Type': 'application/vnd.apple.mpegurl' } })),
  http.get(at(paths.cache), () => HttpResponse.json(report(mock.items))),
  http.put(at('/api/cache/:id'), async ({ params, request }) => {
    const { pinned } = (await request.json()) as { pinned: boolean }
    const found = mock.items.find(i => i.video_id === params.id)
    if (!found) return refused(`${params.id} is not in the cache`, 404)
    mock.items = mock.items.map(i => (i === found ? { ...i, pinned, protected: pinned ? 'pinned' : i.protected === 'pinned' ? null : i.protected } : i))
    return HttpResponse.json({ ...found, pinned })
  }),
  http.delete(at('/api/cache/:id'), ({ params }) => {
    const found = mock.items.find(i => i.video_id === params.id)
    if (!found) return refused(`${params.id} is not in the cache`, 404)
    mock.items = mock.items.filter(i => i !== found)
    return HttpResponse.json({ video_id: found.video_id, freed: found.bytes })
  }),
  http.post(at(paths.evict), () => {
    const gone = mock.items.filter(i => i.state === 'failed')
    mock.items = mock.items.filter(i => i.state !== 'failed')
    return HttpResponse.json({ evicted: gone.map(i => ({ video_id: i.video_id, title: i.title, bytes: i.bytes, score: i.score })), freed: 0, dry_run: false })
  }),
]

// States. A request that never answers is "loading"; 503 is a server that is down. The app's query
// client retries once, so an error shows after about a second (tests turn retries off).

export const systemLoading = http.get(at(paths.system), () => delay('infinite'))
export const systemError = http.get(at(paths.system), down)
export const systemInTrouble = http.get(at(paths.system), () => HttpResponse.json(systemTrouble))

export const settingsLoading = http.get(at(paths.settings), () => delay('infinite'))
export const settingsError = http.get(at(paths.settings), down)
export const saveSettingsFails = http.put(at(paths.settings), down)

export const syncFails = http.post(at(paths.sync), () => refused('The library cannot be read without CLOUDFLARE_API_TOKEN.', 502))

export const channelsLoading = http.get(at(paths.channels), () => delay('infinite'))
export const channelsEmpty = http.get(at(paths.channels), () => HttpResponse.json([]))
export const channelsError = http.get(at(paths.channels), down)

export const shuffleLoading = http.get(at(paths.shuffle), () => delay('infinite'))
export const shuffleEmpty = http.get(at(paths.shuffle), () => HttpResponse.json([]))
export const shuffleError = http.get(at(paths.shuffle), down)

export const videosLoading = http.get(at(paths.videos), () => delay('infinite'))
export const videosError = http.get(at(paths.videos), down)
/** The library holds just these videos (newest first, paged as the server does). */
export const videosFrom = (list: Video[]) => http.get(at(paths.videos), ({ request }) => HttpResponse.json(videoPage(request.url, list)))
/** No videos at all: before the first sync. */
export const videosNone = videosFrom([])
/** A channel with 60 videos: three pages of 24. */
export const videosLong = videosFrom(longChannel)
/** The first page arrives; every page after it fails, so the list shows its Try again row. */
export const videosLaterPageError = http.get(at(paths.videos), ({ request }) =>
  new URL(request.url).searchParams.has('after') ? down() : HttpResponse.json(videoPage(request.url, longChannel)),
)

/** The first page arrives; every page after it never does, so the list shows its skeleton rows. */
export const videosLaterPageLoading = http.get(at(paths.videos), async ({ request }) => {
  if (new URL(request.url).searchParams.has('after')) await delay('infinite')
  return HttpResponse.json(videoPage(request.url, longChannel))
})

export const videoLoading = http.get(at('/api/videos/:id'), () => delay('infinite'))
export const playLoading = http.post(at('/api/videos/:id/play'), () => delay('infinite'))
export const playFails = http.post(at('/api/videos/:id/play'), () => refused('3 videos are already being fetched; try again when one finishes.'))

export const cacheLoading = http.get(at(paths.cache), () => delay('infinite'))
export const cacheError = http.get(at(paths.cache), down)
export const cacheEmpty = http.get(at(paths.cache), () => HttpResponse.json(report([])))
/** Over the 95% line: 960 GB of 1000 GB. */
export const cacheNearlyFull = http.get(at(paths.cache), () => HttpResponse.json(report(mock.items.map(i => ({ ...i, bytes: i.state === 'failed' ? 0 : 192 * 1e9 })))))
export const pinFails = http.put(at('/api/cache/:id'), down)
export const dropFails = http.delete(at('/api/cache/:id'), down)
export const evictFails = http.post(at(paths.evict), down)

/** The video's copy is in one state from the first answer on: `msw.use(...streamIn('fetching'))`. */
export const streamIn = (state: keyof typeof streams) => [
  http.post(at('/api/videos/:id/play'), () => HttpResponse.json(streams[state])),
  http.get(at('/api/videos/:id/stream'), () => HttpResponse.json(streams[state])),
]
