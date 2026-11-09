// The FastAPI server's endpoints (src/tubes/server/app.py) and their shapes. Reads go through
// strata-react's useLoad / useInfiniteLoad with fetchJson, which throws HttpError on a non-2xx
// answer; the screens never call fetch themselves. Every URL is built here, through withBase, so the
// app works at the server's root and behind a reverse proxy at /<prefix>/.
//
// The library (channels and videos) is managed here: Admin's Library page adds channels and videos
// from YouTube and syncs them (the server's catalogue.py); the watching side reads it and plays from
// it, and the cache keeps the fetched copies.
import { HttpError, describeHttpError, fetchJson } from 'strata-react'

export interface Settings {
  data_dir: string
  cache_dir: string
  cache_limit_gb: number
  max_height: number
  player_client: string
  cookies_from_browser: string
  half_life_days: number
  protect_days: number
  ytdlp: string
  ffmpeg: string
}

/** `GET /api/library`: what the library holds. `synced` is when every followed channel was last synced, null before the first. */
export interface LibraryStatus {
  synced: string | null
  channels: number
  /** Videos that can be watched; `hidden` are those YouTube no longer has (deleted or made private), left out of every list. */
  videos: number
  hidden: number
  /** The YouTube key is in the server's environment, so channels can be added and synced. */
  configured: boolean
}

export interface Channel {
  id: string
  title: string
  handle: string | null
  thumbnail: string | null
  /** When this channel was last synced. */
  synced: string | null
  /** Videos held here that can be watched, and those hidden because YouTube no longer has them. */
  videos: number
  hidden?: number
  latest: string | null
  /** YouTube's own counts (null when it hides them). */
  total_videos?: number | null
  subscribers?: number | null
  /** Its uploads are synced. False for a channel only here for videos added one by one. */
  follow?: boolean
  /** Every page of its uploads has been read once. */
  complete?: boolean
  /** A first sync stopped part way and resumes from where it got to. */
  resumable?: boolean
  added?: string | null
}

/** `GET /api/library/sync`: the background sync, one at a time. */
export interface SyncJob {
  running: boolean
  total: number
  done: number
  /** The channel being synced now, by title. */
  current: string | null
  /** New videos so far. */
  added: number
  /** Videos the recheck after a sync of every channel found gone from YouTube, and hid. */
  gone: number
  errors: { channel: string | null; title: string | null; error: string; added?: number }[]
  started: string | null
  finished: string | null
}

/** `POST /api/library`: what was added, and the sync that started for a new channel. */
export type Added = { kind: 'channel'; channel: Channel; sync: SyncJob } | { kind: 'video'; video: Video }

export type CacheState = 'fetching' | 'ready' | 'failed'

export interface Video {
  id: string
  channel_id: string
  channel: string | null
  title: string
  published: string
  duration: number | null
  thumbnail: string | null
  views: number | null
  cache_state: CacheState | null
  cache_bytes: number | null
}

/** `GET /api/videos/{id}`: one video with how often it has been played. */
export interface VideoDetail extends Video {
  plays: number
  last_played: string | null
}

/** `GET /api/videos?...`: one page, newest first. */
export interface VideoPage {
  videos: Video[]
  has_more: boolean
}

/** `GET /api/videos/{id}/stream`: how far the copy has got. `state` none means there is no copy and no fetch. */
export interface Stream {
  state: CacheState | 'none'
  segments: number
  seconds: number
  complete: boolean
  playable: boolean
  error: string | null
  formats: string | null
  plays: number
  last_played: string | null
}

export interface CacheItem {
  video_id: string
  title: string
  channel: string | null
  state: CacheState
  bytes: number
  started: string
  finished: string | null
  formats: string | null
  error: string | null
  pinned: boolean
  plays: number
  last_played: string | null
  score: number
  protected: string | null
}

/** `GET /api/cache`. Sizes are bytes; eviction starts above `high` and stops under `low`. */
export interface CacheReport {
  used: number
  limit: number
  high: number
  low: number
  count: number
  by_state: Record<CacheState, number>
  items: CacheItem[]
}

export interface Evicted { evicted: { video_id: string; title: string; bytes: number; score: number }[]; freed: number; dry_run: boolean }

/** `GET /api/system`. Sizes are bytes. */
export interface SystemStatus {
  version: string
  python: string
  platform: string
  ytdlp: string | null
  ffmpeg: string | null
  can_fetch: boolean
  data_dir: string
  cache_dir: string
  cache: Omit<CacheReport, 'items'>
  fetching: string[]
  disk: { total: number; used: number; free: number }
  library: LibraryStatus
}

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

/** The endpoints, as paths under the server's root. Mock handlers (src/mocks/handlers.ts) match the same paths. */
export const paths = {
  health: '/api/health',
  system: '/api/system',
  settings: '/api/settings',
  library: '/api/library',
  sync: '/api/library/sync',
  channels: '/api/channels',
  channel: (id: string) => `/api/channels/${encodeURIComponent(id)}`,
  restart: (id: string) => `/api/channels/${encodeURIComponent(id)}/restart`,
  videos: '/api/videos',
  shuffle: '/api/videos/shuffle',
  video: (id: string) => `/api/videos/${encodeURIComponent(id)}`,
  play: (id: string) => `/api/videos/${encodeURIComponent(id)}/play`,
  stream: (id: string) => `/api/videos/${encodeURIComponent(id)}/stream`,
  playlist: (id: string) => `/api/media/${encodeURIComponent(id)}/index.m3u8`,
  cache: '/api/cache',
  cacheItem: (id: string) => `/api/cache/${encodeURIComponent(id)}`,
  evict: '/api/cache/evict',
} as const

/** The query keys the screens share, so a write can invalidate every read it changes. */
export const keys = {
  system: ['system'],
  settings: ['settings'],
  channels: ['channels'],
  sync: ['sync'],
  library: ['library'],
  channel: (id: string) => ['channels', id],
  videos: ['videos'],
  list: (filter: VideoFilter) => ['videos', 'list', filter.channel ?? '', filter.q?.trim() ?? ''],
  shuffle: ['videos', 'shuffle'],
  video: (id: string) => ['videos', 'one', id],
  play: (id: string) => ['play', id],
  stream: (id: string) => ['stream', id],
  cache: ['cache'],
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

const send = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  system: () => fetchJson<SystemStatus>(withBase(paths.system)),
  settings: () => fetchJson<Settings>(withBase(paths.settings)),
  saveSettings: (s: Partial<Settings>) => callJson<Settings>(withBase(paths.settings), send('PUT', s)),
  library: () => fetchJson<LibraryStatus>(withBase(paths.library)),
  add: (input: string) => callJson<Added>(withBase(paths.library), send('POST', { input })),
  syncJob: () => fetchJson<SyncJob>(withBase(paths.sync)),
  /** Sync these channels, or every followed one. */
  sync: (channels?: string[]) => callJson<SyncJob>(withBase(paths.sync), send('POST', { channels: channels ?? null })),
  removeChannel: (id: string) => callJson<{ channel: string; videos: number }>(withBase(paths.channel(id)), { method: 'DELETE' }),
  restartChannel: (id: string) => callJson<{ channel: string; videos: number; sync: SyncJob }>(withBase(paths.restart(id)), { method: 'POST' }),
  channels: () => fetchJson<Channel[]>(withBase(paths.channels)),
  channel: (id: string) => fetchJson<Channel>(withBase(paths.channel(id))),
  videos: (filter: VideoFilter, after: string | undefined, signal?: AbortSignal) => fetchJson<VideoPage>(withBase(videosUrl(filter, after)), { signal }),
  shuffle: (count: number) => fetchJson<Video[]>(withBase(`${paths.shuffle}?count=${count}`)),
  video: (id: string) => fetchJson<VideoDetail>(withBase(paths.video(id))),
  play: (id: string) => callJson<Stream>(withBase(paths.play(id)), { method: 'POST' }),
  stream: (id: string) => fetchJson<Stream>(withBase(paths.stream(id))),
  cache: () => fetchJson<CacheReport>(withBase(paths.cache)),
  pin: (id: string, pinned: boolean) => fetchJson<unknown>(withBase(paths.cacheItem(id)), send('PUT', { pinned })),
  dropCopy: (id: string) => fetchJson<{ video_id: string; freed: number }>(withBase(paths.cacheItem(id)), { method: 'DELETE' }),
  evict: () => fetchJson<Evicted>(withBase(paths.evict), send('POST', { dry_run: false })),
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
