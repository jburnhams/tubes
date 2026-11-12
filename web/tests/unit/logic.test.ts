import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { HttpError, colorSchemeScript, format } from 'strata-react'
import { Refused, cursorOf, describeError, folderProblem, numberProblem, runningTime, videosUrl, withBase } from '../../src/api'
import { channels, library, libraryEmpty, syncJobs, longChannel, report, streams, systemStatus, systemTrouble, tile, videos } from '../../src/mocks/fixtures'
import { videoPage } from '../../src/mocks/handlers'
import { attach, problemText, type HlsClass, type HlsInstance, type Media } from '../../src/player'
import { describeCache, describeEvicted } from '../../src/screens/CacheScreen'
import { describeShown, settingsProblems, shownProblems } from '../../src/screens/SettingsScreen'
import { describeSystem, usable } from '../../src/screens/SystemScreen'
import { channelState, describeAdded, describeJob, describeLibrary } from '../../src/screens/LibraryScreen'
import { ago, countFor, episodeLabel, iplayerText, leaving, videoCount, views, viewsAndAge } from '../../src/watch/format'
import { bySeries } from '../../src/watch/ChannelScreen'
import { episodes } from '../../src/mocks/fixtures'
import { isPlaceholder } from '../../src/watch/missing'
import { savedText, settled, waitingText } from '../../src/watch/WatchScreen'
import { describePasted, describeRelated, describeSuggestedBy, describeSuggestions, describeWatched, filterOf, groupChoices, placeOf } from '../../src/screens/SuggestionsScreen'
import { historyUrl, suggestionsUrl } from '../../src/api'
import { describeHistory, fillPeriods, periodLabel, rangeChoices, rangeOf } from '../../src/screens/HistoryScreen'
import { channelHistory, historyStats } from '../../src/mocks/fixtures'
import { describeWatching, elsewhere, libraryState, placeLine } from '../../src/screens/ChannelDetail'
import { historySources, suggestions } from '../../src/mocks/fixtures'
import { suggestionSummary } from '../../src/mocks/handlers'

describe('api helpers', () => {
  it('builds URLs under the base, and a page of videos after a cursor', () => {
    expect(withBase('/api/health')).toBe('/api/health')
    expect(withBase('relative')).toBe('relative')
    expect(videosUrl({}, undefined)).toBe('/api/videos?limit=24')
    expect(videosUrl({ channel: 'UC1', q: '  moon  ' }, '2026-01-01T00:00:00Z|abc', 5)).toBe('/api/videos?channel=UC1&q=moon&after=2026-01-01T00%3A00%3A00Z%7Cabc&limit=5')
    expect(videosUrl({ q: '   ' }, undefined)).toBe('/api/videos?limit=24')
    expect(cursorOf({ published: '2026-01-01T00:00:00Z', id: 'abc' })).toBe('2026-01-01T00:00:00Z|abc')
  })

  it('checks folders and numbers as the server does', () => {
    for (const ok of ['/srv/tubes', '~/tubes', 'C:\\Users\\x', 'D:/data', '\\\\nas\\share']) expect(folderProblem(ok)).toBeUndefined()
    expect(folderProblem('relative/path')).toMatch(/^Use a full path/)
    expect(folderProblem('  ')).toBe('Enter a folder.')
    expect(numberProblem('12.5', 'the limit')).toBeUndefined()
    expect(numberProblem('', 'the limit')).toBe('Enter the limit as a number.')
    expect(numberProblem('abc', 'the limit')).toBe('Enter the limit as a number.')
    expect(numberProblem('0', 'the limit')).toBe('Enter the limit above 0.')
    expect(numberProblem('2.5', 'the count', true)).toBe('Enter the count as a whole number.')
    expect(numberProblem('3', 'the count', true)).toBeUndefined()
  })

  it('writes running times as a clock', () => {
    expect(runningTime(245)).toBe('4:05')
    expect(runningTime(3723.4)).toBe('1:02:03')
    expect(runningTime(null)).toBe('–')
    expect(runningTime(Number.NaN)).toBe('–')
  })

  it('says the server’s own reason when it gave one', () => {
    expect(describeError(new Refused(400, 'Bad Request', '/x', 'No room.'))).toBe('No room.')
    expect(new Refused(400, 'Bad Request', '/x', 'No room.').message).toBe('No room.')
    expect(describeError(new HttpError(503, 'Service Unavailable', '/x'))).toMatch(/503/)
  })
})

describe('missing videos', () => {
  it('takes a 120×90 image as YouTube\'s placeholder unless the small size was asked for', () => {
    const img = (src: string, w = 120, h = 90) => ({ naturalWidth: w, naturalHeight: h, src })
    expect(isPlaceholder(img('https://i.ytimg.com/vi/x/hqdefault.jpg'))).toBe(true)
    expect(isPlaceholder(img('https://i.ytimg.com/vi/x/maxresdefault.jpg?v=1'))).toBe(true)
    expect(isPlaceholder(img('https://i.ytimg.com/vi/x/default.jpg'))).toBe(false)
    expect(isPlaceholder(img('https://i.ytimg.com/vi/x/default.jpg?v=2'))).toBe(false)
    expect(isPlaceholder(img('https://i.ytimg.com/vi/x/hqdefault.jpg', 480, 360))).toBe(false)
    expect(isPlaceholder({ ...img('a'), currentSrc: 'https://i.ytimg.com/vi/x/default.jpg' })).toBe(false)
  })
})

describe('the player', () => {
  const media = (native = '') => {
    const calls: string[] = []
    const m: Media = { src: '', canPlayType: () => native as CanPlayTypeResult, removeAttribute: n => { calls.push(`remove ${n}`) }, load: () => { calls.push('load') } }
    return { m, calls }
  }

  it('plays through hls.js from the start, and says why when it gives up', () => {
    const made: { config: unknown; calls: string[]; listener?: (e: string, d: { fatal?: boolean; type?: string; details?: string }) => void }[] = []
    class FakeHls implements HlsInstance {
      static isSupported() { return true }
      static Events = { ERROR: 'hlsError' }
      rec: (typeof made)[number]
      constructor(config: unknown) { this.rec = { config, calls: [] }; made.push(this.rec) }
      loadSource(src: string) { this.rec.calls.push(`load ${src}`) }
      attachMedia() { this.rec.calls.push('attach') }
      on(event: string, l: (e: string, d: { fatal?: boolean }) => void) { this.rec.calls.push(`on ${event}`); this.rec.listener = l }
      destroy() { this.rec.calls.push('destroy') }
    }
    const problems: string[] = []
    const { m } = media()
    const detach = attach(m, '/api/media/x/index.m3u8', FakeHls as unknown as HlsClass, p => problems.push(p))
    expect(made[0].config).toEqual({ startPosition: 0, lowLatencyMode: false })
    expect(made[0].calls).toEqual(['on hlsError', 'load /api/media/x/index.m3u8', 'attach'])
    made[0].listener!('hlsError', { fatal: false, type: 'networkError' })
    expect(problems).toEqual([])
    made[0].listener!('hlsError', { fatal: true, type: 'networkError' })
    expect(problems).toEqual(['The video stopped arriving from the server. Reload the page to try again.'])
    detach()
    expect(made[0].calls.at(-1)).toBe('destroy')
  })

  it('plays natively where the browser plays HLS, and says when it cannot', () => {
    const none = { isSupported: () => false, Events: { ERROR: 'e' } } as unknown as HlsClass
    const native = media('maybe')
    const detach = attach(native.m, '/p.m3u8', none, () => {})
    expect(native.m.src).toBe('/p.m3u8')
    detach()
    expect(native.calls).toEqual(['remove src', 'load'])
    const problems: string[] = []
    attach(media().m, '/p.m3u8', none, p => problems.push(p))()
    expect(problems).toEqual(['This browser cannot play the stream. Open it in an up-to-date Chrome.'])
  })

  it('turns hls.js errors into sentences', () => {
    expect(problemText({ type: 'mediaError' })).toMatch(/could not decode/)
    expect(problemText({ type: 'otherError', details: 'manifestParsingError' })).toBe('The video could not be played (manifestParsingError).')
    expect(problemText({})).toBe('The video could not be played (unknown error).')
  })
})

describe('the findings', () => {
  it('the watching side writes views and age as video sites do', () => {
    const now = Date.parse('2026-11-09T12:00:00Z')
    expect(videoCount(1)).toBe('1 video')
    expect(videoCount(1234)).toBe('1,234 videos')
    expect(views(null)).toBeNull()
    expect(views(undefined)).toBeNull()
    expect(views(1)).toBe('1 view')
    expect(views(1234)).toBe('1.2K views')
    expect(views(2_500_000)).toBe('2.5M views')
    expect(ago('2026-11-09T11:59:30Z', now)).toBe('just now')
    expect(ago('2026-11-09T12:00:30Z', now)).toBe('just now')
    expect(ago('2026-11-09T11:58:00Z', now)).toBe('2 minutes ago')
    expect(ago('2026-11-09T09:00:00Z', now)).toBe('3 hours ago')
    expect(ago('2026-11-08T12:00:00Z', now)).toBe('1 day ago')
    expect(ago('2026-10-26T12:00:00Z', now)).toBe('2 weeks ago')
    expect(ago('2026-01-20T00:00:00Z', now)).toBe('9 months ago')
    expect(ago('2024-11-01T00:00:00Z', now)).toBe('2 years ago')
    expect(viewsAndAge({ views: 1000, published: '2026-11-08T12:00:00Z' }, now)).toBe('1K views · 1 day ago')
    expect(viewsAndAge({ views: null, published: '2026-11-08T12:00:00Z' }, now)).toBe('1 day ago')
  })

  it('Cache says how full it is and what trimming did', () => {
    expect(describeCache(report([]))).toMatch(/^The cache is empty\./)
    expect(describeCache(report([{ ...report([]).items[0] ?? {}, bytes: 960e9 } as never]))).toMatch(/over the trimming line/)
    expect(describeEvicted({ evicted: [], freed: 0, dry_run: false })).toMatch(/^Nothing needed to go/)
    expect(describeEvicted({ evicted: [{ video_id: 'a', title: 'A', bytes: 5e8, score: 0 }], freed: 5e8, dry_run: false })).toBe(`Freed ${format.bytes(5e8)} from ${format.count(1, 'video')}.`)
  })

  it('System names the first thing that is wrong', () => {
    expect(usable(systemStatus.disk)).toBe(10_000e9)
    expect(describeSystem(systemStatus)).toMatch(/^Everything is ready\./)
    expect(describeSystem(systemStatus, false)).toMatch(/not answering/)
    expect(describeSystem(systemTrouble)).toMatch(/needs Linux or macOS/)
    expect(describeSystem({ ...systemStatus, ytdlp: null })).toMatch(/^yt-dlp is missing/)
    expect(describeSystem({ ...systemStatus, ffmpeg: null })).toMatch(/^ffmpeg is missing/)
    expect(describeSystem({ ...systemStatus, library: { ...libraryEmpty, configured: true } })).toBe('The library is empty. Add a channel on the Library page.')
    expect(describeSystem({ ...systemStatus, library: libraryEmpty })).toMatch(/no YouTube key\. Put YOUTUBE_API_KEY/)
    expect(describeSystem({ ...systemStatus, library: { ...systemStatus.library, synced: null } })).toMatch(/The library has not had a full sync yet, and/)
    expect(describeSystem({ ...systemStatus, disk: { total: 100, used: 98, free: 2 } })).toMatch(/nearly full/)
  })

  it('Shown videos checks its lengths and says what the filters leave out', () => {
    expect(shownProblems({ min: '', max: '', streams: 'current' })).toEqual({ min: undefined, max: undefined })
    expect(shownProblems({ min: '0', max: '90.5', streams: 'all' })).toEqual({ min: undefined, max: undefined })
    expect(shownProblems({ min: 'short', max: '-1', streams: 'current' })).toEqual({ min: 'Enter the shortest length in minutes, or leave it empty for no limit.', max: 'Enter the longest length in minutes, or leave it empty for no limit.' })
    expect(shownProblems({ min: '10', max: '5', streams: 'current' })).toEqual({ min: undefined, max: 'Make this at least the shortest length.' })
    expect(describeShown({ min_seconds: null, max_seconds: null, streams: 'current', filtered: 0 })).toBe('These leave no video out now.')
    expect(describeShown({ min_seconds: 180, max_seconds: null, streams: 'current', filtered: 1 })).toMatch(/^1\svideo is left out by these now\./)
  })

  it('Library says what it follows, how far a sync has got and what each channel is doing', () => {
    expect(describeLibrary(channels, library)).toMatch(/^24\svideos from 3\sfollowed channels\. 1\schannel is still being read back to the first upload\. Every channel was last synced on /)
    expect(describeLibrary(channels.filter(c => c.complete), { ...library, synced: null })).toMatch(/^12\svideos from 2\sfollowed channels\. Not every channel has been synced yet\. 3\svideos are hidden because YouTube no longer has them\.$/)
    expect(describeLibrary(channels, { ...library, hidden: 0 })).toMatch(/synced on [^.]+\.$/)
    expect(describeLibrary(channels, { ...library, hidden: 0, live: 1 })).toMatch(/\. 1\slive or scheduled stream is hidden until it ends\.$/)
    expect(describeLibrary(channels, { ...library, live: 4 })).toMatch(/no longer has them\. 4\slive or scheduled streams are hidden until they end\.$/)
    expect(describeLibrary(channels, { ...library, hidden: 0, filtered: 7 })).toMatch(/\. 7\svideos are left out by the filters in Settings, Shown videos\.$/)
    expect(describeLibrary([], library)).toMatch(/^The library follows no channels yet/)
    expect(describeLibrary(channels, { ...library, configured: false })).toMatch(/YOUTUBE_API_KEY/)
    expect(describeJob(syncJobs.idle)).toBeUndefined()
    expect(describeJob(syncJobs.running)).toMatch(/^Syncing 2 of 3: Night Sky\. 42\snew videos so far\.$/)
    expect(describeJob({ ...syncJobs.running, current: null })).toMatch(/^Starting a sync of 3\schannels\.$/)
    expect(describeJob(syncJobs.done)).toMatch(/^The last sync, of 3\schannels, added 57\snew videos\. 2\svideos gone from YouTube are now hidden\.$/)
    expect(describeJob({ ...syncJobs.done, gone: 1 })).toMatch(/ 1\svideo gone from YouTube is now hidden\.$/)
    expect(describeJob({ ...syncJobs.done, gone: 0, errors: [{ channel: null, title: 'The recheck for videos gone from YouTube', error: 'YouTube could not be reached.' }] })).toMatch(/added 57\snew videos\.$/)   // a failed recheck did not stop the sync
    expect(describeJob(syncJobs.failed)).toMatch(/added 12\snew videos\. 1\schannel failed\.$/)
    expect(describeJob({ ...syncJobs.failed, errors: syncJobs.failed.errors.slice(1) })).toMatch(/added 12\snew videos\. It stopped part way\.$/)
    expect(channels.map(c => channelState(c).word)).toEqual(['Kitchen Science', 'Night Sky', 'Rivers and Coasts', 'Workshop Notes'].map(t => ({ 'Kitchen Science': 'Reading back', 'Night Sky': 'Up to date', 'Rivers and Coasts': 'Not followed', 'Workshop Notes': 'Up to date' })[t]))
    expect(channelState({ ...channels[0], complete: false, resumable: false, synced: null }).word).toBe('Not synced')
    expect(describeAdded({ kind: 'channel', channel: channels[0], sync: syncJobs.running })).toBe('Following Kitchen Science. Its videos are being fetched.')
    expect(describeAdded({ kind: 'video', video: videos[0] })).toBe(`Added “${videos[0].title}” from ${videos[0].channel}.`)
    expect(describeAdded({ kind: 'video', video: { ...videos[0], channel: null } })).toBe(`Added “${videos[0].title}”.`)
  })

  it('Watch says what the frame is waiting for and how much is saved', () => {
    expect(settled(undefined)).toBe(false)
    expect(settled(streams.ready)).toBe(true)
    expect(settled(streams.failed)).toBe(true)
    expect(settled(streams.playable)).toBe(false)
    expect(waitingText(streams.none)).toBe('Asking for the video…')
    expect(waitingText({ ...streams.fetching, formats: null })).toBe('Finding the best copy to fetch…')
    expect(waitingText(streams.fetching)).toBe('Fetching 1080p AV1 + AAC. It starts in a moment.')
    expect(savedText(streams.ready, 606)).toBe('Saved on this server')
    expect(savedText(streams.failed, 606)).toBe('Not saved')
    expect(savedText(streams.none, 606)).toBe('Not saved')
    expect(savedText(streams.playable, 606)).toBe('Fetching: 0:12 of 10:06 so far')
    expect(savedText(streams.playable, null)).toBe('Fetching: 0:12 so far')
  })

  it('Settings checks every field before sending', () => {
    const ok = { cache_dir: '/srv/c', cache_limit_gb: '1000', half_life_days: '30', protect_days: '0', max_height: '1080', player_client: '', cookies_from_browser: '', ytdlp: 'yt-dlp', ffmpeg: 'ffmpeg' }
    expect(Object.values(settingsProblems(ok)).filter(Boolean)).toEqual([])
    const bad = settingsProblems({ ...ok, cache_dir: 'x', cache_limit_gb: '-1', half_life_days: '', protect_days: 'a', ytdlp: ' ', ffmpeg: '' })
    expect(bad).toEqual({
      cache_dir: 'Use a full path from the top of the disk, such as /srv/videos.', cache_limit_gb: 'Enter the limit above 0.', half_life_days: 'Enter the days as a number.',
      protect_days: 'Enter the days as a number.', ytdlp: 'Enter the yt-dlp command, or its full path.', ffmpeg: 'Enter the ffmpeg command, or its full path.',
    })
  })
})

describe('the mock server', () => {
  it('pages videos newest first after a cursor, and matches every word', () => {
    const url = (q: string) => `http://x/api/videos?${q}`
    const first = videoPage(url('limit=2'), longChannel)
    expect(first).toEqual({ videos: longChannel.slice(0, 2), has_more: true })
    expect(videoPage(url(`after=${encodeURIComponent(cursorOf(longChannel[57]))}&limit=24`), longChannel)).toEqual({ videos: longChannel.slice(58), has_more: false })
    expect(videoPage(url('q=BIRD%20box'), videos).videos.map(v => v.title)).toEqual(['Building a bird box'])
    expect(videoPage(url(`channel=${channels[0].id}`), videos).videos.every(v => v.channel_id === channels[0].id)).toBe(true)
    expect(videoPage(url(''), videos).videos).toHaveLength(24)
    expect(tile(10, '1')).toMatch(/^data:image\/svg\+xml;utf8,/)
  })
})

describe('index.html', () => {
  it('inlines the colour-scheme script ThemeProvider expects, so a dark page does not flash light', () => {
    const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
    expect(html).toContain(`<script>${colorSchemeScript()}</script>`)
  })
})

describe('suggestions', () => {
  it('says where they come from, and how far through them', () => {
    const one = { ...suggestionSummary(), sources: [historySources[0]], dismissed: 0, followed: 0 }
    expect(describeSuggestions(one)).toMatch(/^8\schannels from the home history to consider, out of 4,210\swatches\. 4 of them are pointed at by related channels \(2 never watched\), asked about last on 8 Nov 2026\. 1\schannel could not be read last time\.$/)
    expect(describeRelated({ ...one, related: { ...one.related, failed: 0, last: null }, unwatched: 0 })).toMatch(/^4 of them are pointed at by related channels, asked about this week\.$/)
    expect(describeRelated({ ...one, related: { sources: 0, asked: 0, due: 0, failed: 0, last: null } })).toBe('')
    expect(describeRelated({ ...one, open: 0 })).toBe('')
    expect(describeSuggestions({ ...one, sources: [], open: 0, dismissed: 0 })).toMatch(/^No watch history yet\. .* Channels your followed ones point at are added as YouTube is asked about them\.$/)
    expect(describeSuggestions({ ...one, followed: 2, configured: false })).toMatch(/So far 2 followed\. Following and adding need the server’s YouTube key \(YOUTUBE_API_KEY\)\.$/)
    expect(describeSuggestions({ ...one, sources: [], open: 0, dismissed: 0, related: { ...one.related, sources: 0 } })).toMatch(/most watched first\.$/)
  })

  it('describes a channel, the groups to choose from and the filter in the URL', () => {
    const walks = suggestions.find(x => x.title === 'City Walks')!, lathe = suggestions.find(x => x.title === 'Lathe Turning')!
    expect(describeWatched({ ...walks, total_videos: null })).toMatch(/^12\swatches · 12\svideos$/)
    expect(describeWatched({ ...lathe, total_videos: null })).toBe('Never watched')
    expect([0, 1, 2, 3].map(n => describeSuggestedBy({ ...lathe, suggested_by: n, suggested_from: lathe.suggested_from.slice(0, Math.min(n, 2)) }))).toEqual(['', 'Pointed at by Workshop Notes', 'Pointed at by Workshop Notes and Bike Repairs', 'Pointed at by Workshop Notes, Bike Repairs and 1 more'])
    expect(describeSuggestedBy({ ...lathe, suggested_by: 2, suggested_from: [] })).toMatch(/^Pointed at by 2\srelated channels$/)
    expect(filterOf(new URLSearchParams('order=suggested')).order).toBe('suggested')
    expect(filterOf(new URLSearchParams('order=other')).order).toBeUndefined()
    expect(suggestionsUrl({ order: 'suggested' })).toBe('/api/suggestions?order=suggested')
    expect(suggestionsUrl({ pasted: true })).toBe('/api/suggestions?pasted=true')
    expect(filterOf(new URLSearchParams('pasted=true')).pasted).toBe(true)
    expect(describeWatched({ ...lathe, pasted: '2026-11-12T05:00:00+00:00', platform: 'iplayer', total_videos: 3 })).toMatch(/^Pasted .*2026 · 3 on iPlayer$/)
    expect(describePasted({ found: [], already: [], problems: [] })).toBe('Nothing new to suggest.')
    expect(describePasted({ found: [{ input: 'a', platform: 'iplayer', channel_id: 'b1', title: 'A' }], already: [{ input: 'b', title: 'B' }], problems: [{ input: 'c', error: 'No.' }] })).toMatch(/^Added 1\ssuggestion \(1 on iPlayer\)\. Already followed: B\. Not found: “c” \(No\)\.$/)
    const s = suggestionSummary()
    expect(groupChoices({ ...s, ungrouped: 0 }).map(c => c.value)).toEqual(['', '1', '2'])
    expect(groupChoices({ ...s, groups: [{ id: 3, name: 'Empty', named: false, channels: 0 }] }).map(c => c.value)).toEqual(['', 'none'])
    expect(filterOf(new URLSearchParams('group=2&topic=Music&kids=yes&view=dismissed'))).toEqual({ group: '2', topic: 'Music', kids: 'yes', dismissed: true, order: undefined, pasted: undefined })
    const names = new Map([[1, 'Making and mending']])
    expect([suggestions[0], suggestions[1], walks].map(x => placeOf(x, names))).toEqual(['Making and mending · Hobby, Vehicle', 'Entertainment, Film', ''])
    expect(suggestionsUrl({})).toBe('/api/suggestions')
    expect(suggestionsUrl({ group: 'none', topic: 'Pop music', kids: 'no', dismissed: true })).toBe('/api/suggestions?group=none&topic=Pop+music&kids=false&dismissed=true')
    expect(suggestionsUrl({ kids: 'maybe' })).toBe('/api/suggestions')
  })
})

describe('history', () => {
  const now = Date.UTC(2026, 10, 9, 12)
  it('turns a timeframe into start and end', () => {
    expect(rangeOf('30d', now)).toEqual({ start: '2026-10-10T12:00:00+00:00', words: 'in the last 30 days' })
    expect(rangeOf(null, now)).toEqual({ start: '2025-11-09T12:00:00+00:00', words: 'in the last 12 months' })
    expect(rangeOf('nonsense', now).words).toBe('in the last 12 months')
    expect(rangeOf('all', now)).toEqual({ words: 'in all the history' })
    expect(rangeOf('2024', now)).toEqual({ start: '2024-01-01T00:00:00+00:00', end: '2025-01-01T00:00:00+00:00', words: 'in 2024' })
    expect(rangeOf('12m').start).toMatch(/^\d{4}-/)
    expect(rangeChoices([]).map(c => c.value)).toEqual(['12m', '30d', 'all'])
    expect(historyUrl({})).toBe('/api/history')
    expect(historyUrl({ start: 'a', end: 'b', source: 'c' })).toBe('/api/history?start=a&end=b&source=c')
  })

  it('labels and fills periods, and says what was watched', () => {
    expect(periodLabel('2026-03', 'month')).toBe('Mar 2026')
    expect(periodLabel('2026-03-04', 'day')).toBe('4 Mar')
    expect(fillPeriods({ by: 'month', periods: [{ period: '2026-01', watches: 3 }, { period: '2026-03', watches: 1 }] })).toEqual([{ period: '2026-01', watches: 3 }, { period: '2026-02', watches: 0 }, { period: '2026-03', watches: 1 }])
    expect(fillPeriods({ by: 'day', periods: [{ period: '2026-02-28', watches: 1 }, { period: '2026-03-01', watches: 2 }] })).toHaveLength(2)
    expect(fillPeriods({ by: 'day', periods: [{ period: '2026-02-28', watches: 1 }] })).toHaveLength(1)
    const h = { ...historyStats, sources: historySources }
    expect(describeHistory({ ...h, channels_top: [] }, 'in 2026')).toMatch(/channels in 2026\.$/)
    expect(describeHistory({ ...h, channels_top: [{ ...h.channels_top[0], title: null }] }, 'then')).toMatch(/Most watched: UCsuggest000000000000002/)
  })
})

describe('iPlayer episodes on the watching side', () => {
  const now = Date.parse('2026-11-12T12:00:00Z')
  const inDays = (d: number) => new Date(now + d * 86_400_000).toISOString()

  it('labels an episode by its series and number', () => {
    expect(episodeLabel({ series: 'Series 2', episode: 4 })).toBe('S2 E4')
    expect(episodeLabel({ series: 'Series 2', episode: null })).toBe('S2')
    expect(episodeLabel({ series: 'Christmas Special', episode: 1 })).toBe('Christmas Special')
    expect(episodeLabel({ series: null, episode: 7433 })).toBeNull()
    expect(episodeLabel({})).toBeNull()
  })

  it('says when an episode leaves iPlayer only once it is close', () => {
    expect(leaving(inDays(60), now)).toBeNull()
    expect(leaving(inDays(20), now)).toBe('Leaves iPlayer in 2 weeks')
    expect(leaving(inDays(5.5), now)).toBe('Leaves iPlayer in 5 days')
    expect(leaving(inDays(1.2), now)).toBe('Leaves iPlayer in 1 day')
    expect(leaving(inDays(0.5), now)).toBe('Leaves iPlayer today')
    expect(leaving(inDays(-1), now)).toBe('Left iPlayer')
    expect(leaving(null, now)).toBeNull()
    expect(leaving('soon', now)).toBeNull()
  })

  it('puts the series and the leaving date where views go', () => {
    expect(viewsAndAge({ views: null, published: '2026-11-11T12:00:00Z', series: 'Series 1', episode: 2, expires: inDays(3) }, now)).toBe('S1 E2 · 1 day ago · Leaves iPlayer in 3 days')
    expect(viewsAndAge({ views: null, published: '2026-11-11T12:00:00Z', series: null, expires: inDays(300) }, now)).toBe('1 day ago')
  })

  it('counts a programme in episodes, and says how long one is offered', () => {
    expect(countFor({ platform: 'iplayer', videos: 1 })).toBe('1 episode')
    expect(countFor({ platform: 'iplayer', videos: 1020 })).toBe('1,020 episodes')
    expect(countFor({ videos: 3 })).toBe('3 videos')
    expect(iplayerText({ gone: null, expires: '2026-12-12T00:00:00Z' }, now)).toBe('Until 12 Dec 2026')
    expect(iplayerText({ gone: null, expires: inDays(-1) }, now)).toMatch(/^No longer offered/)
    expect(iplayerText({ gone: '2026-11-01T00:00:00Z', expires: null }, now)).toMatch(/^No longer offered/)
    expect(iplayerText({ gone: null }, now)).toBe('Offered')
  })

  it('groups a programme\'s episodes by series as the list reaches them', () => {
    expect(bySeries(episodes).map(([s, vs]) => [s, vs.length])).toEqual([['Series 2', 3], ['Series 1', 3]])
    expect(bySeries([{ ...episodes[0], series: null }, { ...episodes[1], series: undefined }]).map(([s, vs]) => [s, vs.length])).toEqual([[null, 2]])
    expect(bySeries([])).toEqual([])
  })
})

describe('channel panel', () => {
  const o = { channel_id: 'UCx', title: 'X', thumbnail: null, handle: null, library: null, suggestion: null, group: null, configured: true, history: channelHistory('X') }
  it('says how much it was watched, where it sits and what the library holds', () => {
    expect(describeWatching({ ...o, history: { ...o.history, sources: [{ source: 'home', watches: 58 }] } })).toMatch(/^Watched 58\stimes \(41\svideos\) from .* to [^,]*\.$/)
    expect(placeLine(o)).toBe('')
    expect(placeLine({ group: { id: 1, name: 'G', named: true }, suggestion: { ...suggestions[0], topics: [] } })).toBe('Group: G')
    expect(placeLine({ group: null, suggestion: suggestions[0] })).toBe('Hobby, Vehicle')
    expect(libraryState(o).word).toBe('Not in the library')
    expect(elsewhere(o)).toEqual({ href: 'https://www.youtube.com/channel/UCx', label: 'Open on YouTube' })
    expect(elsewhere({ channel_id: 'b0000001', library: { ...channels[0], id: 'b0000001', platform: 'iplayer' } })).toEqual({ href: 'https://www.bbc.co.uk/iplayer/episodes/b0000001', label: 'Open on iPlayer' })
    expect(elsewhere({ channel_id: 'iplayer-films', library: { ...channels[0], id: 'iplayer-films', platform: 'iplayer' } })).toEqual({ href: 'https://www.bbc.co.uk/iplayer/categories/films/featured', label: 'Open on iPlayer' })
  })
})
