// The FastAPI server's endpoints (src/tubes/server/app.py) and their shapes. Reads go through
// strata-react's useLoad / useInfiniteLoad with fetchJson, which throws HttpError on a non-2xx
// answer; the screens never call fetch themselves. Every URL is built here, through withBase, so the
// app works at the server's root and behind a reverse proxy at /<prefix>/.
//
// The library (channels and videos) is managed here: Admin's Library page adds channels and videos
// from YouTube and syncs them (the server's catalogue.py); the watching side reads it and plays from
// it, and the cache keeps the fetched copies.
import { HttpError, describeHttpError, fetchJson } from 'strata-react'
import type { components, Schema } from './api.generated'

/** `GET /api/settings`: every setting (src/tubes/settings.py), typed from the server's declaration; numbers are numbers, `skip_*` one of the modes. */
export type Settings = Schema<'TubesSettings'>

export type SkipMode = Settings['skip_sponsor']

/** A part of a video the player can skip, under SponsorBlock's categories (src/tubes/segments.py). `mute` parts are muted rather than skipped when skipped automatically. */
export type Segment = Schema<'Segment'>

/** A kind of segment, with the server's setting for it. */
export type SegmentKind = Schema<'SegmentKind'>

/** `GET /api/videos/{id}/segments`: what can be skipped, and `error` when its source could not be asked just now. */
export type Segments = Schema<'Segments'>

/** `GET /api/library`: what the library holds. `synced` is when every followed channel was last synced, null before the first. */
export type LibraryStatus = Schema<'LibraryStatus'>

/** Which streams the watching side leaves out: 'current' those live now or scheduled (they cannot be played), 'all' past streams and premieres too. */
export type StreamFilter = 'current' | 'all'

/** `GET /api/library/shown`: which videos the watching side shows, kept in the server's database. Lengths in seconds, null for no limit. */
export type ShownFilters = Schema<'ShownFilters'>

/** How many videos the library offers in one spoken language. */
export type LanguageCount = Schema<'LanguageCount'>

/** Where a channel or video comes from. A BBC iPlayer programme is kept as a channel and its episodes as videos. Absent from older servers (YouTube). */
export type Platform = 'youtube' | 'iplayer' | 'plex'

export type Channel = Schema<'Channel'>

/** Calls to the YouTube Data API, and the quota units they cost, in one slice (a purpose, an endpoint, an hour, a day). */
export interface QuotaTotals {
  calls: number
  units: number
  /** Calls YouTube answered with an error (they still cost their units). */
  failed: number
  /** Of those, the ones refused because the quota was spent. */
  refused: number
}

/** What a YouTube call was made for, as the server names it (quota.py); `other` when no purpose was set. */
export type QuotaPurpose = 'sync' | 'recheck' | 'add' | 'reported' | 'past' | 'suggestions' | 'related' | 'paste' | 'history' | 'other' | (string & {})

/** `GET /api/quota`: the YouTube key's daily quota as this server has counted it. Google has no call that says how much is left. */
export type QuotaUsage = Schema<'QuotaUsage'>

/** `GET /api/library/sync`: the background sync, one at a time. */
export type SyncJob = Schema<'SyncJob'>

/** `POST /api/library`: what was added, and the sync that started for a new channel. */
export type Added = Schema<'AddedChannel'> | Schema<'AddedVideo'>

export type CacheState = 'fetching' | 'partial' | 'ready' | 'failed'     // partial: only its first seconds, prefetched so a play starts at once

export type Video = Schema<'Video'> & Partial<Pick<ContinueVideo, 'resume' | 'progress'>>
/** A Continue watching row: a video with where its last play stopped and how far through that is. */
export type ContinueVideo = Schema<'ContinueVideo'>

/** Where a play or a channel visit was started from (src/tubes/viewing.py): the list, which one (a channel's id, the search words, the
 *  video Up next was beside) and the item's place in it from 0. None at all is a typed, reloaded or shared address. */
export interface From {
  source: 'home' | 'continue' | 'channel' | 'search' | 'up_next' | 'watch' | 'rail' | 'chips' | 'channels'
  detail?: string
  rank?: number
}

/** `POST /api/videos/{id}/play`: the stream status, the play's id (its progress is reported against it) and where it picks up. */
export type Started = Schema<'Started'>

/** `POST /api/plays/{id}`: how the play is going, as the player sees it. `watched` counts each second seen once. */
export interface Progress {
  position: number
  watched: number
  length: number | null
}

/** What the server made of a progress report: none, short, partial, or full (90% and more seen). */
export type Outcome = 'none' | 'short' | 'partial' | 'full'

/** A source as the server keeps it: one of From's, `link` for none, `other` for one it does not know. */
export type PlaySource = From['source'] | 'link' | 'other'

/** `GET /api/plays`: one play with everything kept of it (src/tubes/viewing.py). */
export type Play = Schema<'Play'>

export type PlayPage = Schema<'PlayPage'>

/** Which plays the Viewing page lists. */
export interface PlayFilter {
  outcome?: Outcome
  source?: PlaySource
}

/** `GET /api/plays/summary`: the last `days` of viewing in numbers. */
export type PlaySummary = Schema<'PlaySummary'>

/** `GET /api/channel-views`: one visit to a channel's page. */
export type ChannelVisit = Schema<'ChannelVisit'>

export type ChannelVisitPage = Schema<'ChannelVisitPage'>

/** The cursor after a play or a channel visit: `<at>|<id>`, as the server pages them. */
export const cursorOfRow = (r: { at: string; id: number }) => `${r.at}|${r.id}`

/** `POST /api/videos/check`: what the recheck of these videos found (how many asked about, newly gone, back) and the ids now hidden. */
export type Checked = Schema<'Checked'>

/** `GET /api/videos/{id}`: one video with how often it has been played. */
export type VideoDetail = Schema<'VideoDetail'>

/** `GET /api/videos?...`: one page, newest first. */
export type VideoPage = Schema<'VideoPage'>

/** `GET /api/videos/{id}/stream`: how far the copy has got. `state` none means there is no copy and no fetch. */
export type Stream = Schema<'Stream'>

export type CacheItem = Schema<'CacheItem'>

/** `GET /api/cache`. Sizes are bytes; eviction starts above `high` and stops under `low`. */
export type CacheReport = Schema<'CacheReport'>

export type Evicted = Schema<'Evicted'>

/** `GET /api/system`. Sizes are bytes. */
export type SystemStatus = Schema<'SystemStatus'>

/** One imported watch history (`tubes history import`, or the Suggestions page). */
export type HistorySource = Schema<'HistorySource'>

/** `GET /api/suggestions`: a channel the library could take in, from the watch history or pointed at by related channels. */
export type Suggestion = Schema<'Suggestion'>

/** `POST /api/suggestions/paste`: what a pasted list named. `found` are now suggested, `already` are followed, `problems` say why a line named nothing. */
export type Pasted = Schema<'Pasted'>

export type SuggestionPage = Schema<'SuggestionPage'>

export type SuggestionGroup = Schema<'SuggestionGroup'>

/** `GET /api/suggestions/summary`: what surrounds the list. Counts are of channels. */
export type SuggestionSummary = Schema<'SuggestionSummary'>

/** Of the followed and most watched channels (`sources`), how many YouTube was asked about, how many are due again, and how many failed last time. */
export type RelatedStatus = Schema<'RelatedStatus'>

/** What the list is filtered by; each lives in the page's URL. */
export interface SuggestionFilter { group?: string; topic?: string; kids?: string; dismissed?: boolean; order?: string; pasted?: boolean }

export function suggestionsUrl(f: SuggestionFilter): string {
  const q = new URLSearchParams()
  if (f.group) q.set('group', f.group)
  if (f.topic) q.set('topic', f.topic)
  if (f.kids === 'yes' || f.kids === 'no') q.set('kids', String(f.kids === 'yes'))
  if (f.dismissed) q.set('dismissed', 'true')
  if (f.order === 'suggested') q.set('order', 'suggested')
  if (f.pasted) q.set('pasted', 'true')
  const s = q.toString()
  return s ? `${paths.suggestions}?${s}` : paths.suggestions
}

/** `GET /api/history`: what was watched in a timeframe. `periods` counts watches per `by` (a day, or a month for spans over 92 days). */
export type HistoryStats = Schema<'HistoryStats'>

export interface HistoryFilter { start?: string; end?: string; source?: string }

export function historyUrl(f: HistoryFilter): string {
  const q = new URLSearchParams()
  if (f.start) q.set('start', f.start)
  if (f.end) q.set('end', f.end)
  if (f.source) q.set('source', f.source)
  const s = q.toString()
  return s ? `${paths.history}?${s}` : paths.history
}

/** `GET /api/channels/{id}/overview`: everything known of a channel, whether or not the library has it. */
export type ChannelOverview = Schema<'ChannelOverview'>

export type Refreshed = Schema<'Refreshed'>

// Where the app is served from: '' at the server's own root, '/prefix' behind a reverse proxy. Read
// from the page's base URL: the server gives every page a relative <base> back to its root
// (app.py with_base), and assets are relative (vite.config.ts base './'), so one build works in
// both places. React Router takes the same value as its basename (main.tsx).
export const BASE = typeof document === 'undefined' ? '' : new URL('.', document.baseURI).pathname.replace(/\/$/, '')     // no page (the unit tests run in node): the root
export const withBase = (u: string) => (u.startsWith('/') ? BASE + u : u)

/** Videos per page in a list. */
export const PAGE_SIZE = 24

/** What a list of videos is filtered by: a channel, words in the title, or neither. */
export interface VideoFilter { channel?: string; q?: string }

/** The cursor that asks for the videos after this one (the server orders by date, then id). */
export const cursorOf = (v: Pick<Video, 'published' | 'id'>) => `${v.published}|${v.id}`

/** A page of videos as a URL: the filter, then the cursor after the last one held. */
export function videosUrl(filter: VideoFilter, after: string | undefined, limit = PAGE_SIZE): string {
  const q = new URLSearchParams()
  if (filter.channel) q.set('channel', filter.channel)
  if (filter.q?.trim()) q.set('q', filter.q.trim())
  if (after) q.set('after', after)
  q.set('limit', String(limit))
  return `${paths.videos}?${q}`
}

/** `GET /api/plex`: whether the server has Plex set up and it answers, and its film and TV libraries (src/tubes/plex.py). */
export type PlexStatus = Schema<'PlexStatus'>

export type PlexSection = Schema<'PlexSection'>

/** A film or show as Plex's browser lists it; `thumb` is a Tubes picture address (the token stays on the server). */
export type PlexItem = Schema<'PlexItem'>

export type PlexPage = Schema<'PlexPage'>

/** One value a filter takes in a library (`genre`: {key: '1534', title: 'Animation'}). */
export type PlexChoice = Schema<'PlexChoice'>

/** What a library listing is narrowed by on the Plex page, and kept in the URL. */
export interface PlexFilter {
  section: string
  genre?: string
  contentRating?: string
  title?: string
}

/** The filters of a listing as Plex takes them (only the ones set). */
export function plexParams(f: PlexFilter): Record<string, string> {
  const out: Record<string, string> = {}
  if (f.genre) out.genre = f.genre
  if (f.contentRating) out.contentRating = f.contentRating
  if (f.title?.trim()) out.title = f.title.trim()
  return out
}

/** The endpoints, as paths under the server's root. Mock handlers (src/mocks/handlers.ts) match the same paths. */
export const paths = {
  health: '/api/health',
  system: '/api/system',
  settings: '/api/settings',
  library: '/api/library',
  quota: '/api/quota',
  shown: '/api/library/shown',
  sync: '/api/library/sync',
  channels: '/api/channels',
  channel: (id: string) => `/api/channels/${encodeURIComponent(id)}`,
  overview: (id: string) => `/api/channels/${encodeURIComponent(id)}/overview`,
  restart: (id: string) => `/api/channels/${encodeURIComponent(id)}/restart`,
  videos: '/api/videos',
  shuffle: '/api/videos/shuffle',
  continueWatching: '/api/videos/continue',
  video: (id: string) => `/api/videos/${encodeURIComponent(id)}`,
  progress: (playId: number) => `/api/plays/${playId}`,
  plays: '/api/plays',
  playSummary: '/api/plays/summary',
  channelVisits: '/api/channel-views',
  channelViews: (id: string) => `/api/channels/${encodeURIComponent(id)}/views`,
  play: (id: string) => `/api/videos/${encodeURIComponent(id)}/play`,
  stream: (id: string) => `/api/videos/${encodeURIComponent(id)}/stream`,
  segments: (id: string) => `/api/videos/${encodeURIComponent(id)}/segments`,
  skipping: '/api/skipping',
  check: '/api/videos/check',
  playlist: (id: string) => `/api/media/${encodeURIComponent(id)}/index.m3u8`,
  cache: '/api/cache',
  cacheItem: (id: string) => `/api/cache/${encodeURIComponent(id)}`,
  evict: '/api/cache/evict',
  history: '/api/history',
  suggestions: '/api/suggestions',
  suggestionsSummary: '/api/suggestions/summary',
  suggestionsRefresh: '/api/suggestions/refresh',
  suggestionsImport: '/api/suggestions/import',
  suggestionsPaste: '/api/suggestions/paste',
  suggestion: (id: string) => `/api/suggestions/${encodeURIComponent(id)}`,
  suggestionVideos: (id: string) => `/api/suggestions/${encodeURIComponent(id)}/videos`,
  suggestionGroup: (id: number) => `/api/suggestions/groups/${id}`,
  plex: '/api/plex',
  plexChoices: (section: string, name: string) => `/api/plex/sections/${encodeURIComponent(section)}/filters/${encodeURIComponent(name)}`,
  plexBrowse: '/api/plex/browse',
  plexFollow: '/api/plex/follow',
} as const

/** The query keys the screens share, so a write can invalidate every read it changes. */
export const keys = {
  system: ['system'],
  settings: ['settings'],
  channels: ['channels'],
  sync: ['sync'],
  library: ['library'],
  quota: ['quota'],
  shown: ['library', 'shown'],
  channel: (id: string) => ['channels', id],
  videos: ['videos'],
  list: (filter: VideoFilter) => ['videos', 'list', filter.channel ?? '', filter.q?.trim() ?? ''],
  shuffle: ['videos', 'shuffle'],
  continueWatching: ['videos', 'continue'],
  plays: (f: PlayFilter) => ['viewing', 'plays', f.outcome ?? '', f.source ?? ''],
  playSummary: ['viewing', 'summary'],
  channelVisits: ['viewing', 'channels'],
  /** A visit to a channel's page, recorded once per visit (the location's key). */
  channelView: (id: string, visit: string) => ['channel-view', id, visit],
  video: (id: string) => ['videos', 'one', id],
  play: (id: string) => ['play', id],
  stream: (id: string) => ['stream', id],
  segments: (id: string) => ['segments', id],
  skipping: ['settings', 'skipping'],
  cache: ['cache'],
  suggestions: ['suggestions'],
  history: (f: HistoryFilter) => ['suggestions', 'history', f.start ?? '', f.end ?? '', f.source ?? ''],
  suggestionList: (f: SuggestionFilter) => ['suggestions', 'list', f.group ?? '', f.topic ?? '', f.kids ?? '', f.dismissed ? 'dismissed' : 'open', f.order === 'suggested' ? 'suggested' : 'watched', f.pasted ? 'pasted' : 'all'],
  suggestionSummary: ['suggestions', 'summary'],
  overview: (id: string) => ['suggestions', 'overview', id],
  plex: ['plex'],
  plexChoices: (section: string, name: string) => ['plex', 'choices', section, name],
  plexBrowse: (f: PlexFilter, page: number) => ['plex', 'browse', f.section, f.genre ?? '', f.contentRating ?? '', f.title?.trim() ?? '', page],
} as const

/** A request the server refused with a reason (`{detail}`), such as a fetch that cannot start. The reason is its sentence. */
export class Refused extends HttpError {
  constructor(status: number, statusText: string, url: string, readonly detail: string) {
    super(status, statusText, url)
    this.message = detail
  }
}

/** A write whose refusal says why: like fetchJson, but a non-2xx answer with a `detail` throws Refused with it. */
export async function callJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (r.ok) return (await r.json()) as T
  const detail = await r.json().then((b: { detail?: unknown }) => b.detail, () => undefined)
  throw typeof detail === 'string' ? new Refused(r.status, r.statusText, url, detail) : new HttpError(r.status, r.statusText, url)
}

/** An error for a person: the server's own reason when it gave one, else Strata's sentence for the status. */
export const describeError = (e: unknown) => (e instanceof Refused ? e.detail : describeHttpError(e))

/** Items a page of a Plex library shows. */
export const PLEX_PAGE = 50

/** A request body as the server's model for it declares it (`*In` in server/app.py, through openapi.json → api.generated.ts, `npm run api-types`):
 *  a body that drifts from the server's fails the typecheck. The answers are still typed by hand below, as the server declares no response models yet. */
type In<K extends keyof components['schemas'] & `${string}In`> = Schema<K>

const send = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  system: () => fetchJson<SystemStatus>(withBase(paths.system)),
  settings: () => fetchJson<Settings>(withBase(paths.settings)),
  saveSettings: (s: Partial<Settings>) => callJson<Settings>(withBase(paths.settings), send('PUT', s)),
  library: () => fetchJson<LibraryStatus>(withBase(paths.library)),
  quota: () => fetchJson<QuotaUsage>(withBase(paths.quota)),
  shown: () => fetchJson<ShownFilters>(withBase(paths.shown)),
  saveShown: (f: Partial<Omit<ShownFilters, 'filtered' | 'language_counts'>>) => callJson<ShownFilters>(withBase(paths.shown), send('PUT', f)),
  add: (input: string) => callJson<Added>(withBase(paths.library), send('POST', { input } satisfies In<'AddIn'>)),
  syncJob: () => fetchJson<SyncJob>(withBase(paths.sync)),
  /** Sync these channels, or every followed one. */
  sync: (channels?: string[]) => callJson<SyncJob>(withBase(paths.sync), send('POST', { channels: channels ?? null } satisfies In<'SyncIn'>)),
  removeChannel: (id: string) => callJson<{ channel: string; videos: number }>(withBase(paths.channel(id)), { method: 'DELETE' }),
  restartChannel: (id: string) => callJson<{ channel: string; videos: number; sync: SyncJob }>(withBase(paths.restart(id)), { method: 'POST' }),
  channels: () => fetchJson<Channel[]>(withBase(paths.channels)),
  channel: (id: string) => fetchJson<Channel>(withBase(paths.channel(id))),
  videos: (filter: VideoFilter, after: string | undefined, signal?: AbortSignal) => fetchJson<VideoPage>(withBase(videosUrl(filter, after)), { signal }),
  shuffle: (count: number) => fetchJson<Video[]>(withBase(`${paths.shuffle}?count=${count}`)),
  video: (id: string) => fetchJson<VideoDetail>(withBase(paths.video(id))),
  /** Ask the server to check these videos on YouTube (at most 50): it hides the ones YouTube no longer has. */
  check: (ids: string[]) => callJson<Checked>(withBase(paths.check), send('POST', { ids } satisfies In<'CheckIn'>)),
  /** Start a play. `decodes` is what this browser plays as it is (decodes.ts), so a Plex file is kept as it is where it can be. */
  play: (id: string, from?: From | null, decodes?: string[]) => callJson<Started>(withBase(paths.play(id)), send('POST', { ...(from ?? {}), ...(decodes ? { decodes } : {}) } satisfies In<'FromIn'>)),
  /** How a play is going. `keepalive`, so a report sent as the page closes still arrives. */
  progress: (playId: number, p: Progress) => callJson<{ outcome: Outcome }>(withBase(paths.progress(playId)), { ...send('POST', p satisfies In<'ProgressIn'>), keepalive: true }),
  continueWatching: (limit = 12) => fetchJson<ContinueVideo[]>(withBase(`${paths.continueWatching}?limit=${limit}`)),
  plays: (f: PlayFilter, after: string | undefined, signal?: AbortSignal) => {
    const q = new URLSearchParams()
    if (f.outcome) q.set('outcome', f.outcome)
    if (f.source) q.set('source', f.source)
    if (after) q.set('after', after)
    return fetchJson<PlayPage>(withBase(`${paths.plays}${q.size ? `?${q}` : ''}`), { signal })
  },
  playSummary: () => fetchJson<PlaySummary>(withBase(paths.playSummary)),
  channelVisits: (after: string | undefined, signal?: AbortSignal) => fetchJson<ChannelVisitPage>(withBase(after ? `${paths.channelVisits}?after=${encodeURIComponent(after)}` : paths.channelVisits), { signal }),
  channelView: (id: string, from?: From | null) => callJson<{ id: number }>(withBase(paths.channelViews(id)), send('POST', (from ?? {}) satisfies In<'FromIn'>)),
  stream: (id: string) => fetchJson<Stream>(withBase(paths.stream(id))),
  segments: (id: string) => fetchJson<Segments>(withBase(paths.segments(id))),
  skipping: () => fetchJson<SegmentKind[]>(withBase(paths.skipping)),
  cache: () => fetchJson<CacheReport>(withBase(paths.cache)),
  pin: (id: string, pinned: boolean) => fetchJson<unknown>(withBase(paths.cacheItem(id)), send('PUT', { pinned } satisfies In<'PinIn'>)),
  dropCopy: (id: string) => fetchJson<{ video_id: string; freed: number }>(withBase(paths.cacheItem(id)), { method: 'DELETE' }),
  evict: () => fetchJson<Evicted>(withBase(paths.evict), send('POST', { dry_run: false } satisfies In<'EvictIn'>)),
  overview: (id: string) => fetchJson<ChannelOverview>(withBase(paths.overview(id))),
  history: (f: HistoryFilter) => fetchJson<HistoryStats>(withBase(historyUrl(f))),
  suggestions: (f: SuggestionFilter) => fetchJson<SuggestionPage>(withBase(suggestionsUrl(f))),
  suggestionSummary: () => fetchJson<SuggestionSummary>(withBase(paths.suggestionsSummary)),
  refreshSuggestions: () => callJson<Refreshed & { summary: SuggestionSummary }>(withBase(paths.suggestionsRefresh), { method: 'POST' }),
  pasteSuggestions: (text: string) => callJson<Pasted>(withBase(paths.suggestionsPaste), send('POST', { text } satisfies In<'PasteIn'>)),
  importHistory: (source: string, text: string) => callJson<{ source: string; watches: number; first: string; last: string; refresh: Refreshed }>(withBase(paths.suggestionsImport), send('POST', { source, text } satisfies In<'ImportIn'>)),
  dismiss: (id: string, dismissed: boolean) => callJson<Suggestion>(withBase(paths.suggestion(id)), send('PUT', { dismissed } satisfies In<'DismissIn'>)),
  /** Add the channel's watched videos to the library, without following it. */
  addWatched: (id: string) => callJson<{ added: number; already: number; missing: number }>(withBase(paths.suggestionVideos(id)), { method: 'POST' }),
  plex: () => fetchJson<PlexStatus>(withBase(paths.plex)),
  plexChoices: (section: string, name: string) => fetchJson<PlexChoice[]>(withBase(paths.plexChoices(section, name))),
  plexBrowse: (f: PlexFilter, page: number, size = PLEX_PAGE) => {
    const q = new URLSearchParams({ section: f.section, start: String(page * size), size: String(size), ...plexParams(f) })
    return fetchJson<PlexPage>(withBase(`${paths.plexBrowse}?${q}`))
  },
  /** Follow a show or a film by its key, or a library listing with filters as a channel of its own. */
  plexFollow: (body: { key: string } | { section: string; params: Record<string, string>; title: string }) => callJson<Added>(withBase(paths.plexFollow), send('POST', body satisfies In<'FollowIn'>)),
  renameGroup: (id: number, name: string) => callJson<SuggestionGroup>(withBase(paths.suggestionGroup(id)), send('PUT', { name } satisfies In<'NameIn'>)),
}

/** What is wrong with a folder, or undefined. The server takes absolute paths only, `~` included. */
export function folderProblem(value: string): string | undefined {
  const v = value.trim()
  if (!v) return 'Enter a folder.'
  return /^(\/|~|[A-Za-z]:[\\/]|\\\\)/.test(v) ? undefined : 'Use a full path from the top of the disk, such as /srv/videos.'
}

/** What is wrong with a positive number field, or undefined. */
export function numberProblem(value: string, what: string, whole = false): string | undefined {
  const n = Number(value.trim())
  if (!value.trim() || !Number.isFinite(n)) return `Enter ${what} as a number.`
  if (n <= 0) return `Enter ${what} above 0.`
  return whole && !Number.isInteger(n) ? `Enter ${what} as a whole number.` : undefined
}

/** A running time as a clock: 4:05, 1:02:03. Unknown is a dash. */
export function runningTime(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '–'
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60
  const two = (n: number) => String(n).padStart(2, '0')
  return h ? `${h}:${two(m)}:${two(r)}` : `${m}:${two(r)}`
}
