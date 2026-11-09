// Sample data for the mock server (handlers.ts): the same records answer the unit and integration
// tests, every Storybook story and the visual suite's screenshots, so a screen looks the same in
// each. Dates are fixed, so screenshots do not change from day to day. Pictures are flat SVG
// tiles as data URLs, so nothing is fetched from outside.
import type { CacheItem, CacheReport, Channel, LibraryStatus, Settings, Stream, SyncJob, SystemStatus, Video } from '../api'

export const GB = 1e9

export const defaultSettings: Settings = {
  data_dir: '/srv/tubes',
  cache_dir: '/srv/tubes/cache',
  cache_limit_gb: 1000,
  max_height: 1080,
  player_client: 'visionos',
  cookies_from_browser: '',
  half_life_days: 30,
  protect_days: 7,
  ytdlp: 'yt-dlp',
  ffmpeg: 'ffmpeg',
}

/** A flat picture of one colour with a lighter disc whose place depends on `label`: a stand-in thumbnail. No text: an SVG inside an <img>
 *  draws text in the machine's own fonts, which the visual suite cannot pin, and another machine's glyphs failed the CI screenshots. */
export function tile(hue: number, label: string): string {
  const n = [...label].reduce((sum, ch) => sum + ch.charCodeAt(0), 0)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180"><rect width="320" height="180" fill="hsl(${hue} 45% 55%)"/><circle cx="${60 + (n * 37) % 200}" cy="${50 + (n * 23) % 80}" r="36" fill="hsl(${hue} 45% 72%)"/></svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

const names = [
  { id: 'UCworkshop00000000000001', title: 'Workshop Notes', handle: '@workshopnotes', hue: 28 },
  { id: 'UCnightsky00000000000002', title: 'Night Sky', handle: '@nightsky', hue: 230 },
  { id: 'UCkitchen000000000000003', title: 'Kitchen Science', handle: '@kitchenscience', hue: 140 },
  { id: 'UCcoasts0000000000000004', title: 'Rivers and Coasts', handle: null, hue: 190 },
]

const topics: Record<string, string[]> = {
  'Workshop Notes': ['Building a bird box', 'Sharpening a chisel', 'A shelf from one board', 'Gluing up a table top', 'Fixing a wobbly chair', 'Cutting dovetails by hand'],
  'Night Sky': ['Finding the Plough', 'What a meteor shower is', 'The Moon through binoculars', 'Why stars twinkle', 'Saturn this month', 'Spotting the space station'],
  'Kitchen Science': ['Why bread rises', 'Making butter in a jar', 'Red cabbage colour test', 'Crystals from salt', 'How ice cream freezes', 'Floating eggs'],
  'Rivers and Coasts': ['Where a river starts', 'How waves shape cliffs', 'Rock pools at low tide', 'Why the sea is salty', 'Building a sand dam', 'Following a stream'],
}

const day = (n: number) => new Date(Date.UTC(2026, 0, 20) - n * 86_400_000).toISOString().replace('.000Z', 'Z')

/** `n` videos per channel, newest first by channel order, one every few days back from 20 January 2026. */
export function makeVideos(perChannel = 6): Video[] {
  const out: Video[] = []
  names.forEach((c, ci) => {
    for (let i = 0; i < perChannel; i++) {
      const id = `${c.title.slice(0, 2).toLowerCase()}${String(i).padStart(9, '0')}`.slice(0, 11)
      out.push({
        id, channel_id: c.id, channel: c.title,
        title: topics[c.title][i % topics[c.title].length] + (i >= topics[c.title].length ? ` (part ${Math.floor(i / topics[c.title].length) + 1})` : ''),
        published: day(i * 4 + ci), duration: 240 + ((i * 97 + ci * 31) % 1500), thumbnail: tile(c.hue, String(i + 1)), views: 1000 + i * 37,
        cache_state: null, cache_bytes: null,
      })
    }
  })
  return out.sort((a, b) => (a.published === b.published ? b.id.localeCompare(a.id) : b.published.localeCompare(a.published)))
}

export const videos: Video[] = makeVideos().map(v =>
  v.id === 'wo000000000' ? { ...v, cache_state: 'ready', cache_bytes: 0.42 * GB }
    : v.id === 'ni000000000' ? { ...v, cache_state: 'fetching', cache_bytes: 0.05 * GB }
      : v.id === 'ki000000001' ? { ...v, cache_state: 'failed', cache_bytes: 0 } : v)

/** A long channel, for paging: 60 videos, so its list needs three pages of 24. */
export const longChannel: Video[] = Array.from({ length: 60 }, (_, i) => ({
  ...videos[0], id: `lo${String(i).padStart(9, '0')}`, title: `Episode ${60 - i}`, published: day(i), thumbnail: tile(28, String(60 - i)), cache_state: null, cache_bytes: null,
}))

/** How far each sample channel's sync has got: two up to date, one still reading back, one only here for videos added one by one. */
const syncState: Record<string, Partial<Channel>> = {
  'Workshop Notes': { follow: true, complete: true, resumable: false, total_videos: 6, subscribers: 12_400 },
  'Night Sky': { follow: true, complete: true, resumable: false, total_videos: 6, subscribers: 88_100 },
  'Kitchen Science': { follow: true, complete: false, resumable: true, total_videos: 214, subscribers: 3_050 },
  'Rivers and Coasts': { follow: false, complete: false, resumable: false, total_videos: null, subscribers: null, synced: null },     // no counts: carried over from before they were kept
}

export const channels: Channel[] = names.map(c => {
  const own = videos.filter(v => v.channel_id === c.id)
  return { id: c.id, title: c.title, handle: c.handle, thumbnail: c.handle ? tile(c.hue, c.title.slice(0, 1)) : null, synced: '2026-11-09T06:00:00Z', videos: own.length, latest: own[0]?.published ?? null, added: '2026-01-10T12:00:00Z', ...syncState[c.title] }
}).sort((a, b) => a.title.localeCompare(b.title))

/** The background sync in each sample state. `idle` is a server that has not synced since it started. */
const idle: SyncJob = { running: false, total: 0, done: 0, current: null, added: 0, errors: [], started: null, finished: null }
export const syncJobs = {
  idle,
  running: { ...idle, running: true, total: 3, done: 1, current: 'Night Sky', added: 42, started: '2026-11-09T11:58:00+00:00' } as SyncJob,
  done: { ...idle, total: 3, done: 3, added: 57, started: '2026-11-09T11:58:00+00:00', finished: '2026-11-09T11:59:10+00:00' } as SyncJob,
  failed: { ...idle, total: 3, done: 3, added: 12, started: '2026-11-09T11:58:00+00:00', finished: '2026-11-09T11:59:10+00:00', errors: [{ channel: 'UCkitchen000000000000003', title: 'Kitchen Science', error: 'YouTube refused the request (403: the key has used its quota for today (it resets at midnight Pacific time)).' }, { channel: null, title: null, error: 'The sync stopped: the database could not be reached.' }] } as SyncJob,
}

export const library: LibraryStatus = { synced: '2026-11-09T06:00:00+00:00', channels: channels.length, videos: videos.length, configured: true }
export const libraryEmpty: LibraryStatus = { synced: null, channels: 0, videos: 0, configured: false }
/** A key, but no channels yet. */
export const libraryNew: LibraryStatus = { ...libraryEmpty, configured: true }

const none: Stream = { state: 'none', segments: 0, seconds: 0, complete: false, playable: false, error: null, formats: null, plays: 0, last_played: null }

/** What `/stream` answers for a video in each sample state. */
export const streams = {
  none,
  fetching: { ...none, state: 'fetching', formats: '1080p AV1 + AAC', plays: 1, last_played: '2026-11-09T09:00:00+00:00' } as Stream,
  playable: { ...none, state: 'fetching', segments: 3, seconds: 12, playable: true, formats: '1080p AV1 + AAC', plays: 1, last_played: '2026-11-09T09:00:00+00:00' } as Stream,
  ready: { ...none, state: 'ready', segments: 152, seconds: 606, complete: true, playable: true, formats: '1080p VP9 + AAC', plays: 4, last_played: '2026-11-09T09:00:00+00:00' } as Stream,
  failed: { ...none, state: 'failed', error: 'Video unavailable. This video is private.', formats: null, plays: 1, last_played: '2026-11-09T09:00:00+00:00' } as Stream,
}

const item = (v: Video, over: Partial<CacheItem>): CacheItem => ({
  video_id: v.id, title: v.title, channel: v.channel, state: 'ready', bytes: 0.4 * GB, started: '2026-11-01T10:00:00+00:00', finished: '2026-11-01T10:03:00+00:00',
  formats: '1080p AV1 + AAC', error: null, pinned: false, plays: 1, last_played: '2026-11-02T18:00:00+00:00', score: 0.6, protected: null, ...over,
})

export const cacheItems: CacheItem[] = [
  item(videos[0], { plays: 9, score: 7.1, last_played: '2026-11-09T08:00:00+00:00', protected: 'played in the last day', bytes: 0.42 * GB }),
  item(videos[3], { pinned: true, plays: 3, score: 2.2, protected: 'pinned', bytes: 0.61 * GB, formats: '1080p VP9 + AAC' }),
  item(videos[5], { plays: 2, score: 0.9 }),
  item(videos[1], { state: 'fetching', bytes: 0.05 * GB, finished: null, plays: 1, score: 1, last_played: '2026-11-09T09:00:00+00:00', protected: 'fetching' }),
  item(videos[8], { plays: 0, score: 0, last_played: null, protected: 'not played yet', bytes: 0.33 * GB }),
  item(videos[2], { state: 'failed', bytes: 0, error: 'Video unavailable. This video is private.', formats: null, plays: 1, score: 0.1, finished: '2026-11-03T10:00:00+00:00' }),
]

/** Builds a report from items: what the server works out (sizes in bytes, thresholds at 95% and 90%). */
export function report(items: CacheItem[], limit = 1000 * GB): CacheReport {
  const by = (s: CacheItem['state']) => items.filter(i => i.state === s).length
  return { used: items.reduce((n, i) => n + i.bytes, 0), limit, high: 0.95 * limit, low: 0.9 * limit, count: items.length, by_state: { fetching: by('fetching'), ready: by('ready'), failed: by('failed') }, items }
}

export const systemStatus: SystemStatus = {
  version: '0.1.0',
  python: '3.13.1',
  platform: 'Linux 6.17.7-arch1-1',
  ytdlp: '2026.10.26',
  ffmpeg: 'ffmpeg version 8.0 Copyright (c) 2000-2025 the FFmpeg developers',
  can_fetch: true,
  data_dir: defaultSettings.data_dir,
  cache_dir: defaultSettings.cache_dir,
  cache: (({ items: _items, ...rest }) => rest)(report(cacheItems)),
  fetching: [videos[1].id],
  disk: { total: 10_000 * GB, used: 6_120 * GB, free: 3_880 * GB },
  library,
}

/** The same server with yt-dlp missing, nothing synced and its disk nearly full. */
export const systemTrouble: SystemStatus = { ...systemStatus, ytdlp: null, can_fetch: false, library: libraryEmpty, fetching: [], disk: { total: 10_000 * GB, used: 9_700 * GB, free: 300 * GB } }
