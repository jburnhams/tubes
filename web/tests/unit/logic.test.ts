import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { HttpError, colorSchemeScript, format } from 'strata-react'
import { Refused, cursorOf, describeError, folderProblem, numberProblem, runningTime, videosUrl, withBase } from '../../src/api'
import { channels, library, libraryEmpty, syncJobs, longChannel, report, streams, systemStatus, systemTrouble, tile, videos } from '../../src/mocks/fixtures'
import { videoPage } from '../../src/mocks/handlers'
import { attach, problemText, type HlsClass, type HlsInstance, type Media } from '../../src/player'
import { describeCache, describeEvicted } from '../../src/screens/CacheScreen'
import { settingsProblems } from '../../src/screens/SettingsScreen'
import { describeSystem, usable } from '../../src/screens/SystemScreen'
import { channelState, describeAdded, describeJob, describeLibrary } from '../../src/screens/LibraryScreen'
import { ago, videoCount, views, viewsAndAge } from '../../src/watch/format'
import { isPlaceholder } from '../../src/watch/missing'
import { savedText, settled, waitingText } from '../../src/watch/WatchScreen'
import { describeSuggestions, describeWatched, filterOf, groupChoices, placeOf } from '../../src/screens/SuggestionsScreen'
import { suggestionsUrl } from '../../src/api'
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

  it('Library says what it follows, how far a sync has got and what each channel is doing', () => {
    expect(describeLibrary(channels, library)).toMatch(/^24\svideos from 3\sfollowed channels\. 1\schannel is still being read back to the first upload\. Every channel was last synced on /)
    expect(describeLibrary(channels.filter(c => c.complete), { ...library, synced: null })).toMatch(/^12\svideos from 2\sfollowed channels\. Not every channel has been synced yet\. 3\svideos are hidden because YouTube no longer has them\.$/)
    expect(describeLibrary(channels, { ...library, hidden: 0 })).toMatch(/synced on [^.]+\.$/)
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
    expect(describeSuggestions(one)).toMatch(/^6\schannels from the home history to consider, out of 4,210\swatches\.$/)
    expect(describeSuggestions({ ...one, followed: 2, configured: false })).toMatch(/So far 2 followed\. Following and adding need the server’s YouTube key \(YOUTUBE_API_KEY\)\.$/)
    expect(describeSuggestions({ ...one, sources: [] })).toMatch(/^No watch history yet\./)
  })

  it('describes a channel, the groups to choose from and the filter in the URL', () => {
    expect(describeWatched({ ...suggestions[6], total_videos: null })).toMatch(/^12\swatches · 12\svideos$/)
    const s = suggestionSummary()
    expect(groupChoices({ ...s, ungrouped: 0 }).map(c => c.value)).toEqual(['', '1', '2'])
    expect(groupChoices({ ...s, groups: [{ id: 3, name: 'Empty', named: false, channels: 0 }] }).map(c => c.value)).toEqual(['', 'none'])
    expect(filterOf(new URLSearchParams('group=2&topic=Music&kids=yes&view=dismissed'))).toEqual({ group: '2', topic: 'Music', kids: 'yes', dismissed: true })
    const names = new Map([[1, 'Making and mending']])
    expect([suggestions[0], suggestions[1], suggestions[6]].map(x => placeOf(x, names))).toEqual(['Making and mending · Hobby, Vehicle', 'Entertainment, Film', ''])
    expect(suggestionsUrl({})).toBe('/api/suggestions')
    expect(suggestionsUrl({ group: 'none', topic: 'Pop music', kids: 'no', dismissed: true })).toBe('/api/suggestions?group=none&topic=Pop+music&kids=false&dismissed=true')
    expect(suggestionsUrl({ kids: 'maybe' })).toBe('/api/suggestions')
  })
})
