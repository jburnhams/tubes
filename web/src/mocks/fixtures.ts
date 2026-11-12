// Sample data for the mock server (handlers.ts): the same records answer the unit and integration
// tests, every Storybook story and the visual suite's screenshots, so a screen looks the same in
// each. Dates are fixed, so screenshots do not change from day to day. Pictures are flat SVG
// tiles as data URLs, so nothing is fetched from outside.
import type { CacheItem, CacheReport, Channel, HistorySource, HistoryStats, LibraryStatus, RelatedStatus, Settings, Stream, Suggestion, SuggestionGroup, SyncJob, SystemStatus, Video } from '../api'

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
        cache_state: null, cache_bytes: null, gone: null,
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
  'Kitchen Science': { follow: true, complete: false, resumable: true, total_videos: 214, subscribers: 3_050, hidden: 3 },
  'Rivers and Coasts': { follow: false, complete: false, resumable: false, total_videos: null, subscribers: null, synced: null },     // no counts: carried over from before they were kept
}

export const channels: Channel[] = names.map(c => {
  const own = videos.filter(v => v.channel_id === c.id)
  return { id: c.id, title: c.title, handle: c.handle, thumbnail: c.handle ? tile(c.hue, c.title.slice(0, 1)) : null, synced: '2026-11-09T06:00:00Z', videos: own.length, latest: own[0]?.published ?? null, added: '2026-01-10T12:00:00Z', ...syncState[c.title] }
}).sort((a, b) => a.title.localeCompare(b.title))

/** The background sync in each sample state. `idle` is a server that has not synced since it started. */
const idle: SyncJob = { running: false, total: 0, done: 0, current: null, added: 0, gone: 0, errors: [], started: null, finished: null }
export const syncJobs = {
  idle,
  running: { ...idle, running: true, total: 3, done: 1, current: 'Night Sky', added: 42, started: '2026-11-09T11:58:00+00:00' } as SyncJob,
  done: { ...idle, total: 3, done: 3, added: 57, gone: 2, started: '2026-11-09T11:58:00+00:00', finished: '2026-11-09T11:59:10+00:00' } as SyncJob,
  failed: { ...idle, total: 3, done: 3, added: 12, started: '2026-11-09T11:58:00+00:00', finished: '2026-11-09T11:59:10+00:00', errors: [{ channel: 'UCkitchen000000000000003', title: 'Kitchen Science', error: 'YouTube refused the request (403: the key has used its quota for today (it resets at midnight Pacific time)).' }, { channel: null, title: null, error: 'The sync stopped: the database could not be reached.' }] } as SyncJob,
}

export const library: LibraryStatus = { synced: '2026-11-09T06:00:00+00:00', channels: channels.length, videos: videos.length, hidden: 3, configured: true }
export const libraryEmpty: LibraryStatus = { synced: null, channels: 0, videos: 0, hidden: 0, configured: false }
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

/** The watch histories behind the suggestions: two, as from two accounts. */
export const historySources: HistorySource[] = [
  { source: 'home', watches: 4_210, channels: 380, first: '2019-03-02T18:00:00+00:00', last: '2026-10-30T19:12:00+00:00' },
  { source: 'work', watches: 1_288, channels: 140, first: '2023-01-10T08:30:00+00:00', last: '2026-09-02T12:40:00+00:00' },
]

const suggestion = (n: number, title: string, hue: number, s: Partial<Suggestion>): Suggestion => ({
  channel_id: `UCsuggest${String(n).padStart(15, '0')}`, title, handle: `@${title.toLowerCase().replace(/[^a-z]/g, '')}`, thumbnail: tile(hue, title), watches: 10, videos: 8,
  first: '2024-02-01T10:00:00+00:00', last: '2026-10-01T10:00:00+00:00', score: 5, group_id: null, subscribers: 10_000, total_videos: 120, topics: [], made_for_kids: null,
  missing: false, dismissed: null, in_library: false, suggested_by: 0, related_score: 0, suggested_from: [], platform: 'youtube', pasted: null,
  link: `https://www.youtube.com/channel/UCsuggest${String(n).padStart(15, '0')}`, ...s,
})

/** One no history has watches for, only pointed at by related channels. */
const related = (n: number, title: string, hue: number, s: Partial<Suggestion>): Suggestion =>
  suggestion(n, title, hue, { watches: 0, videos: 0, first: null, last: null, score: 0, ...s })

/** Channels from the history, best score first: two groups (one named), one ungrouped, one made for kids, one with a video in the library;
 * some also pointed at by related channels, and two that only related channels point at (one with no picture or details yet). */
export const suggestions: Suggestion[] = [
  suggestion(1, 'Bike Repairs', 20, { watches: 412, videos: 380, score: 140.2, group_id: 1, topics: ['Hobby', 'Vehicle'], total_videos: 2_900, last: '2026-10-28T19:00:00+00:00', suggested_by: 2, related_score: 1.3, suggested_from: ['Workshop Notes', 'Model Railways'] }),
  suggestion(2, 'Puppet Theatre', 300, { watches: 248, videos: 89, score: 120.5, group_id: 2, topics: ['Entertainment', 'Film'], made_for_kids: true, last: '2026-10-30T07:00:00+00:00' }),
  suggestion(3, 'Model Railways', 100, { watches: 180, videos: 172, score: 61.9, group_id: 1, topics: ['Hobby'], last: '2026-09-07T20:00:00+00:00', in_library: true, suggested_by: 1, related_score: 0.33, suggested_from: ['Workshop Notes'] }),
  suggestion(4, 'Garden Birds', 140, { watches: 96, videos: 90, score: 33.4, group_id: 1, topics: ['Lifestyle'], total_videos: null }),
  suggestion(5, 'Counting Songs', 50, { watches: 51, videos: 39, score: 30.1, group_id: 2, topics: ['Music'], made_for_kids: true }),
  suggestion(6, 'Old Synth Sounds', 260, { watches: 105, videos: 48, score: 9.8, topics: ['Electronic music', 'Music'], last: '2023-08-02T22:00:00+00:00', thumbnail: null }),
  related(8, 'Lathe Turning', 40, { group_id: 1, topics: ['Hobby'], total_videos: 640, suggested_by: 5, related_score: 3.6, suggested_from: ['Workshop Notes', 'Bike Repairs', 'Model Railways'] }),
  related(9, 'Canal Boats', 220, { thumbnail: null, handle: null, subscribers: null, total_videos: null, suggested_by: 2, related_score: 0.5, suggested_from: ['Garden Birds', 'Workshop Notes'] }),
  suggestion(7, 'City Walks', 200, { watches: 12, videos: 12, score: 2.1, group_id: null, dismissed: '2026-11-01T10:00:00+00:00', last: null }),
]

/** Asking YouTube about related channels: every source asked this week, one failed. */
export const relatedStatus: RelatedStatus = { sources: 24, asked: 24, due: 0, failed: 1, last: '2026-11-08T08:00:00+00:00' }

/** What the stand-in finds when a list is pasted, by what was typed (a link or a name, any case): a YouTube channel and an iPlayer programme. */
export const pasteable: Record<string, Suggestion> = {
  'https://www.youtube.com/@ropemaking': related(20, 'Rope Making', 10, { handle: '@ropemaking', topics: ['Hobby'], total_videos: 210 }),
  'https://www.bbc.co.uk/iplayer/episodes/b0000001': related(21, 'Harbour Lights', 190, { channel_id: 'b0000001', platform: 'iplayer', handle: null, subscribers: null, total_videos: 12, link: 'https://www.bbc.co.uk/iplayer/episodes/b0000001' }),
}
pasteable['harbour lights'] = pasteable['https://www.bbc.co.uk/iplayer/episodes/b0000001']

export const suggestionGroups: SuggestionGroup[] = [
  { id: 1, name: 'Making and mending', named: true, channels: 3 },
  { id: 2, name: 'Puppet Theatre, Counting Songs', named: false, channels: 2 },
]

/** What was watched, by month over a year (with one quiet month), the top channels (one followed) and videos. */
export const historyStats: Omit<HistoryStats, 'sources'> = {
  watches: 2_140, videos: 1_610, channels: 212, first: '2025-11-12T08:00:00+00:00', last: '2026-10-30T19:12:00+00:00', by: 'month',
  periods: [['2025-11', 120], ['2025-12', 210], ['2026-01', 340], ['2026-02', 180], ['2026-04', 90], ['2026-05', 260], ['2026-06', 310], ['2026-07', 150], ['2026-08', 140], ['2026-09', 190], ['2026-10', 150]].map(([period, watches]) => ({ period: String(period), watches: Number(watches) })),
  channels_top: [
    { channel_id: 'UCsuggest000000000000002', title: 'Puppet Theatre', watches: 248, videos: 89, last: '2026-10-30T07:00:00+00:00', followed: false },
    { channel_id: 'UCworkshop00000000000001', title: 'Workshop Notes', watches: 201, videos: 150, last: '2026-10-28T19:00:00+00:00', followed: true },
    { channel_id: 'UCsuggest000000000000001', title: 'Bike Repairs', watches: 96, videos: 90, last: '2026-09-07T20:00:00+00:00', followed: false },
  ],
  videos_top: [
    { video_id: 'pu000000001', title: 'The puppet who lost his hat', channel_id: 'UCsuggest000000000000002', channel: 'Puppet Theatre', watches: 14, last: '2026-10-30T07:00:00+00:00' },
    { video_id: 'wo000000000', title: 'Building a bird box', channel_id: 'UCworkshop00000000000001', channel: 'Workshop Notes', watches: 9, last: '2026-10-20T19:00:00+00:00' },
    { video_id: 'gone0000001', title: null, channel_id: null, channel: null, watches: 3, last: '2026-02-01T10:00:00+00:00' },
  ],
}

/** The same over 30 days, by day. */
export const historyDays: Omit<HistoryStats, 'sources'> = {
  ...historyStats, watches: 64, videos: 50, channels: 12, by: 'day', first: '2026-10-11T08:00:00+00:00',
  periods: Array.from({ length: 20 }, (_, i) => ({ period: `2026-10-${String(i + 11).padStart(2, '0')}`, watches: (i * 7) % 6 + (i % 4 === 0 ? 0 : 1) })).filter(p => p.watches > 0),
}
