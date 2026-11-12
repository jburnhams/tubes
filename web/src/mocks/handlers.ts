// The mock server: MSW handlers for every endpoint the app calls, answering like a healthy server.
// One set serves the jsdom tests (Node, tests/utils/server.ts), Storybook (a service worker,
// .storybook/preview.tsx) and the visual suite (Node, strata-visual.config.ts), so the app's real
// fetch, query and DataView code runs in all three and nothing is a module mock.
//
// The named handlers below each replace one route to put a test, story or screenshot into another
// state: `server.use(videosError)` in a test, `msw.use(videosError)` in a story's beforeEach,
// `states: { error: [videosError] }` in the visual config.
import { delay, http, HttpResponse } from 'msw'
import { cursorOf, paths, type CacheItem, type Channel, type HistorySource, type Settings, type Stream, type Suggestion, type SuggestionGroup, type SuggestionSummary, type SyncJob, type Video, type VideoPage } from '../api'
import { cacheItems, channels, defaultSettings, historyDays, historySources, historyStats, library, libraryNew, longChannel, relatedStatus, report, streams, suggestionGroups, suggestions, syncJobs, systemStatus, systemTrouble, tile, videos } from './fixtures'

/** What the mock server holds. Writes change it, so a test can pin a copy and see it pinned. */
export const mock = {
  settings: { ...defaultSettings } as Settings,
  items: [...cacheItems] as CacheItem[],
  plays: [] as string[],
  /** What /stream answers, by video id; anything else answers `ready`. */
  streams: {} as Record<string, Stream>,
  synced: library.synced,
  channels: [...channels] as Channel[],
  job: syncJobs.idle as SyncJob,
  /** Video ids YouTube no longer has, as POST /api/videos/check finds them; `checks` records each call's ids. */
  gone: [] as string[],
  checks: [] as string[][],
  /** The suggestions as the server holds them; following one (POST /api/library with its id) takes it off the list. */
  suggestions: [...suggestions] as Suggestion[],
  followed: [] as string[],
  groups: [...suggestionGroups] as SuggestionGroup[],
  sources: [...historySources] as HistorySource[],
  related: { ...relatedStatus },
  /** Each import's {source, text}. */
  imports: [] as { source: string; text: string }[],
}

/** Back to the healthy state: call between tests and stories. */
export function resetMock() {
  mock.settings = { ...defaultSettings }
  mock.items = [...cacheItems]
  mock.plays = []
  mock.streams = {}
  mock.synced = library.synced
  mock.channels = [...channels]
  mock.job = syncJobs.idle
  mock.gone = []
  mock.checks = []
  mock.suggestions = [...suggestions]
  mock.followed = []
  mock.groups = [...suggestionGroups]
  mock.sources = [...historySources]
  mock.related = { ...relatedStatus }
  mock.imports = []
}

/** `GET /api/suggestions?...` from the held suggestions, as history.suggestions does. */
export function suggestionPage(url: string, list: Suggestion[]) {
  const p = new URL(url).searchParams
  const items = list
    .filter(x => !mock.followed.includes(x.channel_id) && !x.missing)
    .filter(x => (p.get('dismissed') === 'true' ? !!x.dismissed : !x.dismissed))
    .filter(x => !p.get('group') || (p.get('group') === 'none' ? x.group_id === null : String(x.group_id) === p.get('group')))
    .filter(x => !p.get('topic') || x.topics.includes(p.get('topic')!))
    .filter(x => !p.get('kids') || (p.get('kids') === 'true' ? x.made_for_kids === true : x.made_for_kids !== true))
    .sort(p.get('order') === 'suggested' ? (a, b) => b.suggested_by - a.suggested_by || b.related_score - a.related_score || b.score - a.score : (a, b) => b.score - a.score || b.related_score - a.related_score)
  return { items, total: items.length }
}

/** `GET /api/suggestions/summary` from the held suggestions. */
export function suggestionSummary(): SuggestionSummary {
  const open = mock.suggestions.filter(x => !mock.followed.includes(x.channel_id) && !x.dismissed)
  const topics = new Map<string, number>()
  for (const x of open) for (const t of x.topics) topics.set(t, (topics.get(t) ?? 0) + 1)
  return {
    sources: mock.sources,
    groups: mock.groups.map(g => ({ ...g, channels: open.filter(x => x.group_id === g.id).length })),
    ungrouped: open.filter(x => x.group_id === null).length,
    topics: [...topics].map(([name, channels]) => ({ name, channels })).sort((a, b) => b.channels - a.channels || a.name.localeCompare(b.name)),
    kids: open.filter(x => x.made_for_kids).length,
    open: open.length,
    dismissed: mock.suggestions.filter(x => x.dismissed && !mock.followed.includes(x.channel_id)).length,
    followed: mock.followed.length,
    refreshed: '2026-11-08T09:00:00+00:00',
    configured: true,
    suggested: open.filter(x => x.suggested_by).length,
    unwatched: open.filter(x => !x.watches).length,
    related: mock.related,
  }
}

/** A sync as the server starts one: running, over these channels (every followed one by default). */
function startSync(ids?: string[] | null): SyncJob {
  if (mock.job.running && ids) return (mock.job = { ...mock.job, total: mock.job.total + ids.length })    // the running sync takes them next
  const todo = ids ?? mock.channels.filter(c => c.follow !== false).map(c => c.id)
  mock.job = { ...syncJobs.idle, running: true, total: todo.length, current: mock.channels.find(c => c.id === todo[0])?.title ?? null, started: '2026-11-09T12:00:00+00:00' }
  return mock.job
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
const shown = () => videos.filter(v => !mock.gone.includes(v.id))

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
  http.get(at(paths.library), () => HttpResponse.json({ ...library, synced: mock.synced, channels: mock.channels.length })),
  // Adding: "@..." or a channel id is a channel (followed, its sync starts); an 11-character id is a video; "@nobody" is not on YouTube.
  http.post(at(paths.library), async ({ request }) => {
    const { input } = (await request.json()) as { input: string }
    if (input === '@nobody') return refused('YouTube has no channel @nobody.', 404)
    if (/^[\w-]{11}$/.test(input)) return HttpResponse.json({ kind: 'video', video: { ...videos[0], id: input, title: 'A video added on its own' } })
    if (mock.suggestions.some(x => x.channel_id === input)) mock.followed.push(input)
    const known = mock.channels.find(c => c.id === input || c.handle === input)
    const channel: Channel = known ? { ...known, follow: true } : { id: 'UCnew0000000000000000005', title: 'Paper Planes', handle: input.startsWith('@') ? input : null, thumbnail: tile(320, 'P'), synced: null, videos: 0, latest: null, follow: true, complete: false, resumable: false, total_videos: 48, subscribers: 900, added: '2026-11-09T12:00:00Z' }
    mock.channels = known ? mock.channels.map(c => (c === known ? channel : c)) : [...mock.channels, channel].sort((a, b) => a.title.localeCompare(b.title))
    return HttpResponse.json({ kind: 'channel', channel, sync: startSync([channel.id]) })
  }),
  http.get(at(paths.sync), () => HttpResponse.json(mock.job)),
  http.post(at(paths.sync), async ({ request }) => {
    if (mock.job.running) return refused('A sync is already running; it says how far it has got.', 409)
    const body = (await request.json().catch(() => null)) as { channels?: string[] | null } | null
    return HttpResponse.json(startSync(body?.channels))
  }),
  http.get(at(paths.channels), () => HttpResponse.json(mock.channels)),
  http.get(at('/api/channels/:id'), ({ params }) => {
    const c = mock.channels.find(c => c.id === params.id)
    return c ? HttpResponse.json(c) : refused(`There is no channel ${params.id} in the library.`, 404)
  }),
  http.delete(at('/api/channels/:id'), ({ params }) => {
    const c = mock.channels.find(c => c.id === params.id)
    if (!c) return refused(`There is no channel ${params.id} in the library.`, 404)
    mock.channels = mock.channels.filter(x => x !== c)
    return HttpResponse.json({ channel: c.id, videos: c.videos })
  }),
  http.post(at('/api/channels/:id/restart'), ({ params }) => {
    const c = mock.channels.find(c => c.id === params.id)
    if (!c) return refused(`There is no channel ${params.id} in the library.`, 404)
    mock.channels = mock.channels.map(x => (x === c ? { ...x, videos: 0, complete: false, synced: null } : x))
    return HttpResponse.json({ channel: c.id, videos: c.videos, sync: mock.job.running ? mock.job : startSync([c.id]) })
  }),
  // A video in `mock.gone` is left out of the lists and says when it went, as the server does once it is hidden.
  http.get(at(paths.shuffle), ({ request }) => HttpResponse.json(shown().slice(0, Number(new URL(request.url).searchParams.get('count') ?? 24)))),
  http.get(at(paths.videos), ({ request }) => HttpResponse.json(videoPage(request.url, shown()))),
  http.get(at('/api/videos/:id'), ({ params }) => {
    const found = find(String(params.id))
    const v = found && mock.gone.includes(found.id) ? { ...found, gone: '2026-11-09T12:00:00+00:00' } : found
    const plays = mock.plays.filter(p => p === params.id).length
    return v ? HttpResponse.json({ ...v, plays, last_played: plays ? '2026-11-09T09:30:00+00:00' : null }) : refused(`There is no video ${params.id} in the library.`, 404)
  }),
  http.post(at(paths.check), async ({ request }) => {
    const { ids } = (await request.json()) as { ids: string[] }
    mock.checks.push(ids)
    const hidden = ids.filter(id => mock.gone.includes(id))
    return HttpResponse.json({ checked: ids.length, gone: hidden.length, back: 0, hidden })
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
  http.get(at(paths.suggestionsSummary), () => HttpResponse.json(suggestionSummary())),
  http.post(at(paths.suggestionsRefresh), () => HttpResponse.json({ channels: mock.suggestions.length, groups: mock.groups.length, grouped: 5, looked_up: 0, missing: 0, error: null, summary: suggestionSummary() })),
  http.post(at(paths.suggestionsImport), async ({ request }) => {
    const b = (await request.json()) as { source: string; text: string }
    if (!b.text.includes('Watched')) return refused('That is not a Google Takeout watch history (watch-history.json or watch-history.html).')
    mock.imports.push(b)
    const watches = (b.text.match(/Watched/g) ?? []).length
    mock.sources = [...mock.sources.filter(x => x.source !== b.source), { source: b.source, watches, channels: 1, first: '2026-01-01T10:00:00+00:00', last: '2026-02-01T10:00:00+00:00' }].sort((a, c) => a.source.localeCompare(c.source))
    return HttpResponse.json({ source: b.source, watches, first: '2026-01-01T10:00:00+00:00', last: '2026-02-01T10:00:00+00:00', refresh: { channels: 7, groups: 2, grouped: 5, looked_up: 0, missing: 0, error: null } })
  }),
  // History: a start within the last 40 days answers by day; a source answers the same, smaller; a year before the history answers nothing.
  http.get(at(paths.history), ({ request }) => {
    const p = new URL(request.url).searchParams
    const start = p.get('start'), end = p.get('end')
    const base = end && end < '2019-06' ? { ...historyStats, watches: 0, videos: 0, channels: 0, periods: [], channels_top: [], videos_top: [], first: null, last: null }
      : start && start >= '2026-09-30' ? historyDays : historyStats
    const one = p.get('source') ? { watches: Math.round(base.watches / 2) } : {}
    const followed = (id: string) => mock.followed.includes(id) || mock.channels.some(c => c.id === id && c.follow !== false)
    return HttpResponse.json({ ...base, ...one, channels_top: base.channels_top.map(c => ({ ...c, followed: c.followed || followed(c.channel_id) })), sources: mock.sources, configured: true })
  }),
  http.get(at(paths.suggestions), ({ request }) => HttpResponse.json(suggestionPage(request.url, mock.suggestions))),
  http.put(at('/api/suggestions/groups/:id'), async ({ params, request }) => {
    const { name } = (await request.json()) as { name: string }
    const g = mock.groups.find(x => String(x.id) === params.id)
    if (!g) return refused(`There is no group ${String(params.id)}.`, 404)
    const named = { ...g, name: name.trim() || g.name, named: !!name.trim() }
    mock.groups = mock.groups.map(x => (x === g ? named : x))
    return HttpResponse.json(named)
  }),
  http.put(at('/api/suggestions/:id'), async ({ params, request }) => {
    const { dismissed } = (await request.json()) as { dismissed: boolean }
    const x = mock.suggestions.find(y => y.channel_id === params.id)
    if (!x) return refused(`There is no suggestion ${String(params.id)}.`, 404)
    const now = { ...x, dismissed: dismissed ? '2026-11-09T12:00:00+00:00' : null }
    mock.suggestions = mock.suggestions.map(y => (y === x ? now : y))
    return HttpResponse.json(now)
  }),
  http.post(at('/api/suggestions/:id/videos'), ({ params }) => {
    const x = mock.suggestions.find(y => y.channel_id === params.id)
    if (!x) return refused(`There is no suggestion ${String(params.id)}.`, 404)
    mock.suggestions = mock.suggestions.map(y => (y === x ? { ...y, in_library: true } : y))
    return HttpResponse.json({ added: x.videos - 2, already: x.in_library ? 2 : 0, missing: x.in_library || x.videos > 300 ? 2 : 0 })
  }),
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

export const syncFails = http.post(at(paths.sync), () => refused('YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.', 503))
/** The sync in one state from the first answer on: `msw.use(syncIn('running'))`. */
export const syncIn = (state: keyof typeof syncJobs) => http.get(at(paths.sync), () => HttpResponse.json(syncJobs[state]))
/** The server has no YouTube key: nothing can be added or synced. */
export const libraryNoKey = http.get(at(paths.library), () => HttpResponse.json({ ...library, configured: false }))
/** A key and no channels: the first visit. */
export const libraryFirstVisit = [http.get(at(paths.library), () => HttpResponse.json(libraryNew)), http.get(at(paths.channels), () => HttpResponse.json([]))]
export const libraryLoading = http.get(at(paths.library), () => delay('infinite'))
export const addFails = http.post(at(paths.library), () => down())
export const removeChannelFails = http.delete(at('/api/channels/:id'), down)

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

export const suggestionsLoading = http.get(at(paths.suggestions), () => delay('infinite'))
export const suggestionsError = http.get(at(paths.suggestions), down)
export const summaryLoading = http.get(at(paths.suggestionsSummary), () => delay('infinite'))
export const summaryError = http.get(at(paths.suggestionsSummary), down)
/** No history imported yet: the page is the import form. */
export const suggestionsFirstVisit = http.get(at(paths.suggestionsSummary), () => HttpResponse.json({ ...suggestionSummary(), sources: [], groups: [], topics: [], open: 0, dismissed: 0, ungrouped: 0, kids: 0, suggested: 0, unwatched: 0, related: { sources: 0, asked: 0, due: 0, failed: 0, last: null } }))
/** No history imported, but the followed channels' related channels are in: only those are suggested. */
export const suggestionsRelatedOnly = [
  http.get(at(paths.suggestionsSummary), () => HttpResponse.json({ ...suggestionSummary(), sources: [], groups: [], ungrouped: 2, open: 2, dismissed: 0, suggested: 2, unwatched: 2, kids: 0, topics: [{ name: 'Hobby', channels: 1 }], related: { sources: 19, asked: 19, due: 0, failed: 0, last: '2026-11-08T08:00:00+00:00' } })),
  http.get(at(paths.suggestions), ({ request }) => HttpResponse.json(suggestionPage(request.url, mock.suggestions.filter(x => !x.watches).map(x => ({ ...x, group_id: null }))))),
]
/** YouTube has not been asked about related channels yet. */
export const relatedNotAsked = http.get(at(paths.suggestionsSummary), () => HttpResponse.json({ ...suggestionSummary(), suggested: 0, unwatched: 0, related: { sources: 24, asked: 0, due: 24, failed: 0, last: null } }))
/** The server has no YouTube key: nothing can be followed or added. */
export const suggestionsNoKey = http.get(at(paths.suggestionsSummary), () => HttpResponse.json({ ...suggestionSummary(), configured: false }))
export const followFails = http.post(at(paths.library), () => refused('YouTube refused the request (403: the key has used its quota for today (it resets at midnight Pacific time)).', 502))
export const addWatchedFails = http.post(at('/api/suggestions/:id/videos'), down)
export const dismissFails = http.put(at('/api/suggestions/:id'), down)
export const renameFails = http.put(at('/api/suggestions/groups/:id'), down)
export const refreshQuota = http.post(at(paths.suggestionsRefresh), () => HttpResponse.json({ channels: 7, groups: 2, grouped: 5, looked_up: 0, missing: 0, error: 'YouTube refused the request (403: quota).', summary: suggestionSummary() }))
/** More channels match than the server sends: the list says it shows the first ones. */
export const suggestionsTruncated = http.get(at(paths.suggestions), ({ request }) => HttpResponse.json({ ...suggestionPage(request.url, mock.suggestions), total: 250 }))
export const historyLoading = http.get(at(paths.history), () => delay('infinite'))
export const historyError = http.get(at(paths.history), down)
export const historyNone = http.get(at(paths.history), () => HttpResponse.json({ ...historyStats, watches: 0, videos: 0, channels: 0, periods: [], channels_top: [], videos_top: [], first: null, last: null, sources: [] }))
/** One account only: no account choice. */
export const historyOneAccount = http.get(at(paths.history), () => HttpResponse.json({ ...historyStats, sources: [historySources[0]] }))
/** The server has no YouTube key: no channel can be followed from History. */
export const historyNoKey = http.get(at(paths.history), () => HttpResponse.json({ ...historyStats, sources: historySources, configured: false }))
