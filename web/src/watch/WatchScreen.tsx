// The one question: "Can I watch this now?" Laid out as the old Tubes watch page: the player, the
// title, the channel, a grey box with the views, age and how much of the video is on this server,
// and Up next beside it (below it on a narrow screen).
//
// Opening the page is the play: it records the play and starts the fetch unless the video is already
// in the cache (POST /play). The server writes the copy as HLS while it downloads, so the player
// starts as soon as the first few seconds are on disk (`playable`), usually two or three seconds,
// and follows the copy as it grows. Until then the frame says what is happening; if the fetch fails
// it says why, with Fetch again. The play is a useLoad keyed on the video with gcTime 0: a query,
// not an effect, so React's double-mount in development does not record two plays, and leaving and
// coming back records a new one. The stream status is polled each second until the copy is whole or failed.
// A failed fetch reports the video as missing (missing.ts); when YouTube no longer has it, the frame
// and the details say so rather than leaving the reason to yt-dlp's wording.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { DataView, describeHttpError, HttpError, type Load, useAsyncAction, MediaPlayer, useLoad } from 'strata-react'
import { api, describeError, keys, paths, withBase, type Segment, type SegmentKind, type Segments, type Stream, type VideoDetail } from '../api'
import { attachStream } from '../player'
import { Avatar, RowsSkeleton, VideoRow, useChannelsById } from './cards'
import { countFor, iplayerText, runningTime, viewsAndAge } from './format'
import { reportMissing, useHidden } from './missing'
import { at, modesOf, place, segmentKey, shown, skippedText, skipText } from './skip'
import { Pill, trouble } from './Shown'

/** How often the copy's progress is read while it is still arriving. */
export const POLL_MS = 1000
/** How many videos Up next offers. */
export const UP_NEXT = 12

/** Polling stops once the copy is whole or the fetch has failed. */
export const settled = (s: Stream | undefined) => !!s && (s.complete || s.state === 'failed')

/** What the frame says while the first seconds are on their way. */
export function waitingText(s: Stream): string {
  if (s.state === 'none') return 'Asking for the video…'
  return s.formats ? `Fetching ${s.formats}. It starts in a moment.` : 'Finding the best copy to fetch…'
}

/** How much of the video is on this server, in words. */
export function savedText(s: Stream, duration: number | null): string {
  if (s.complete) return 'Saved on this server'
  if (s.state === 'failed' || s.state === 'none') return 'Not saved'
  return duration ? `Fetching: ${runningTime(s.seconds)} of ${runningTime(duration)} so far` : `Fetching: ${runningTime(s.seconds)} so far`
}

/** The player, with the parts that can be skipped (skip.ts): an "ask" part shows a Skip button over the picture while it plays, an "auto"
 *  part is skipped (or muted) as it starts with an Undo for a few seconds, and every part not off is drawn on a strip under the player.
 *  The player is strata-react's `MediaPlayer` (its own controls on a desktop, the browser's on a touch screen), playing the stream through
 *  the HLS engine (player.ts), `growing` while the copy is still being fetched so playback that catches up waits and carries on, and
 *  saying a failure with Try again. MediaPlayer does not hand out its element, so skipping finds the <video> inside it to seek and mute. */
export function Player({ src, title, segments, kinds, length, growing }: { src: string; title: string; segments: Segment[]; kinds: SegmentKind[]; length: number | null; growing?: string }) {
  const box = useRef<HTMLDivElement>(null)
  const video = () => box.current!.querySelector('video')!     // MediaPlayer kind="video" always draws one
  const [t, setT] = useState(0)
  const [elementLength, setElementLength] = useState<number | null>(null)
  // Placed by the library's length while the copy grows (the element only knows the part fetched so far), else by the element's own.
  const duration = growing !== undefined ? (length ?? elementLength) : (elementLength ?? length)
  useEffect(() => {
    const el = video()
    const read = () => { setT(el.currentTime); setElementLength(Number.isFinite(el.duration) && el.duration > 0 ? el.duration : null) }
    el.addEventListener('timeupdate', read)
    el.addEventListener('durationchange', read)
    return () => { el.removeEventListener('timeupdate', read); el.removeEventListener('durationchange', read) }
  }, [])
  const seek = (to: number) => { video().currentTime = to; setT(to) }
  const [notice, setNotice] = useState<Segment>()
  const done = useRef(new Set<string>())                    // parts skipped, or let play, once: never acted on again
  const muted = useRef<Segment | undefined>(undefined)
  const parts = shown(segments, modesOf(kinds))
  const modes = modesOf(kinds)
  // An automatic part is acted on whatever else plays at the time (an Ask intro around an automatic sponsor read does not hold it back).
  const auto = parts.find(s => modes[s.category] === 'auto' && t >= s.start && t < s.end && !done.current.has(segmentKey(s)))
  const leftMute = !!muted.current && !(t >= muted.current.start && t < muted.current.end)
  useEffect(() => {
    const el = video()
    if (leftMute) { el.muted = false; muted.current = undefined }
    if (!auto) return
    done.current.add(segmentKey(auto))
    if (auto.action === 'mute') { el.muted = true; muted.current = auto } else seek(auto.end)
    setNotice(auto)
  }, [auto, leftMute])
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(undefined), NOTICE_MS)
    return () => clearTimeout(timer)
  }, [notice])
  const asking = at(parts.filter(s => modes[s.category] === 'ask' && !done.current.has(segmentKey(s))), t)
  const skip = (s: Segment) => { done.current.add(segmentKey(s)); seek(s.end) }
  const undo = (s: Segment) => { setNotice(undefined); if (s.action === 'mute') { video().muted = false; muted.current = undefined } else seek(s.start) }
  const overlay = 'pointer-events-auto absolute right-3 bottom-3 rounded-tube-sm bg-tube-badge px-4 py-2 text-tube-sm font-medium text-tube-on-screen'
  return (
    <div className="grid gap-1">
      <div ref={box} className="relative">
        <MediaPlayer kind="video" label={title} sources={[{ src, title, duration: length ?? undefined }]} attach={attachStream} autoPlay growing={growing !== undefined ? { status: growing } : undefined} />
        {/* Over the picture (the top of the player, a 16:9 box), not over the controls under it. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 aspect-video">
          {asking && <button type="button" onClick={() => skip(asking)} className={`${overlay} hover:opacity-85`}>{skipText(asking, kinds)} ›</button>}
          {notice && !asking && (
            <p role="status" className={`${overlay} flex items-center gap-3`}>
              {skippedText(notice, kinds)}
              <button type="button" onClick={() => undo(notice)} className="font-bold underline underline-offset-2">Undo</button>
            </p>
          )}
        </div>
      </div>
      <Timeline parts={parts} kinds={kinds} duration={duration} />
    </div>
  )
}

const NOTICE_MS = 5000

/** Why the skippable parts are not known, or '' when they are (or are still being asked for): the read failed, or the server could not ask
 *  their source just now (it still sends what it had). */
export function skipTrouble(load: Load<Segments>): string {
  if (load.status === 'error') return `The parts to skip could not be read: ${load.message}`
  if (load.status === 'ready' && load.data.error) return `The parts to skip could not be looked up: ${load.data.error}`
  return ''
}

/** The skippable parts as coloured marks along a strip the width of the picture (in SponsorBlock's colours), named for screen readers. */
function Timeline({ parts, kinds, duration }: { parts: Segment[]; kinds: SegmentKind[]; duration: number | null }) {
  const placed = parts.map(s => [s, place(s, duration)] as const).filter((x): x is readonly [Segment, { left: number; width: number }] => !!x[1])
  if (!placed.length) return null
  const label = (s: Segment) => `${kinds.find(k => k.id === s.category)!.label} ${runningTime(s.start)}–${runningTime(s.end)}`   // a part is only shown for a kind the server named
  return (
    <div role="img" aria-label={`Parts that can be skipped: ${placed.map(([s]) => label(s)).join(', ')}`} className="relative mx-3 h-1.5 overflow-hidden rounded-full bg-tube-chip">
      {placed.map(([s, p]) => (
        <span key={segmentKey(s)} title={label(s)} className="absolute inset-y-0" style={{ left: `${p.left}%`, width: `max(${p.width}%, 2px)`, background: `var(--tube-seg-${s.category}, var(--tube-quiet))` }} />
      ))}
    </div>
  )
}

function Frame({ children }: { children: ReactNode }) {
  return <div className="grid aspect-video w-full place-items-center rounded-tube bg-tube-screen p-6 text-center text-tube-on-screen">{children}</div>
}

function Stage({ v }: { v: VideoDetail }) {
  const queryClient = useQueryClient()
  const byId = useChannelsById()
  const channel = byId.get(v.channel_id)
  const play = useLoad({ queryKey: keys.play(v.id), queryFn: () => api.play(v.id), staleTime: Infinity, gcTime: 0, describeError })
  const stream = useLoad({
    queryKey: keys.stream(v.id), queryFn: () => api.stream(v.id), enabled: play.status === 'ready',
    refetchInterval: q => (settled(q.state.data) ? false : POLL_MS),
  })
  const again = useAsyncAction(async () => {
    await queryClient.resetQueries({ queryKey: keys.play(v.id) })
    await queryClient.invalidateQueries({ queryKey: keys.stream(v.id) })
  }, { describeError })
  const skips = useLoad({ queryKey: keys.segments(v.id), queryFn: () => api.segments(v.id), staleTime: Infinity })   // what can be skipped: nothing (not an error) until it answers
  const s = play.status !== 'ready' ? undefined : stream.status === 'ready' ? stream.data : play.data
  const failed = s?.state === 'failed'
  useEffect(() => { if (failed) reportMissing(v.id) }, [failed, v.id])
  // A fetch that worked tells the server the video is there after all (it clears `gone`): read the video again so this page agrees.
  const whole = !!s?.complete
  useEffect(() => { if (whole && v.gone) void queryClient.invalidateQueries({ queryKey: keys.video(v.id) }) }, [whole, v.gone, v.id, queryClient])
  const hidden = useHidden()
  const gone = !!v.gone || hidden.has(v.id)

  return (
    <div className="grid content-start gap-3">
      {play.status === 'error' ? (
        <Frame><div role="alert" className="grid justify-items-center gap-2"><p className="text-tube-lg font-medium">This video cannot start now</p><p className="text-tube-sm opacity-80">{play.message}</p></div></Frame>
      ) : !s ? (
        <Frame><p role="status" className="text-tube-base opacity-80">Asking for the video…</p></Frame>
      ) : s.state === 'failed' ? (
        <Frame>
          <div className="grid justify-items-center gap-3">
            <p className="text-tube-lg font-medium">{gone ? 'This video is no longer on YouTube' : 'This video could not be fetched'}</p>
            <p className="text-tube-sm opacity-80">{gone ? 'It was removed or made private, and there is no copy on this server.' : (s.error ?? 'The fetch stopped without saying why.')}</p>
            {/* Resetting the play puts the frame back to "Asking for the video…" at once, so the button needs no pending state. */}
            <button type="button" onClick={() => void again.run()} className="h-9 rounded-full bg-tube-on-screen px-4 text-tube-sm font-medium text-tube-screen hover:opacity-85">Fetch again</button>
          </div>
        </Frame>
      ) : s.playable ? (
        <Player src={withBase(paths.playlist(v.id))} title={v.title} segments={skips.status === 'ready' ? skips.data.segments : []} kinds={skips.status === 'ready' ? skips.data.categories : []} length={v.duration} growing={s.complete ? undefined : savedText(s, v.duration)} />
      ) : (
        <Frame><p role="status" className="text-tube-base opacity-80">{waitingText(s)}</p></Frame>
      )}
      {s?.playable && !failed && skipTrouble(skips) && (
        <p role="status" className="flex flex-wrap items-center gap-3 text-tube-xs text-tube-quiet">
          {skipTrouble(skips)} The video plays as it is.
          {skips.status === 'error' && <Pill onClick={skips.retry}>Try again</Pill>}
        </p>
      )}

      <h1 className="text-tube-lg font-bold">{v.title}</h1>
      <Link to={`/channels/${encodeURIComponent(v.channel_id)}`} className="flex w-fit items-center gap-3">
        <Avatar channel={channel} name={v.channel} size="size-10" />
        <span className="grid">
          <span className="text-tube-base font-medium">{v.channel ?? channel?.title ?? 'Channel'}</span>
          {channel && <span className="text-tube-xs text-tube-quiet">{countFor(channel)}</span>}
        </span>
      </Link>
      <dl className="grid gap-1 rounded-tube bg-tube-chip p-3 text-tube-sm">
        <div className="font-medium"><dt className="sr-only">Views and age</dt><dd>{viewsAndAge(v)}</dd></div>
        <div className="flex gap-2"><dt className="text-tube-quiet">Length</dt><dd className="tabular-nums">{runningTime(v.duration)}</dd></div>
        {gone && v.platform !== 'iplayer' && <div className="flex gap-2"><dt className="text-tube-quiet">On YouTube</dt><dd>No longer there (removed or made private)</dd></div>}
        {v.platform === 'iplayer' && <div className="flex gap-2"><dt className="text-tube-quiet">On iPlayer</dt><dd>{iplayerText(v)}</dd></div>}
        {s && (
          <>
            <div className="flex gap-2"><dt className="text-tube-quiet">Copy</dt><dd className="tabular-nums">{savedText(s, v.duration)}</dd></div>
            <div className="flex gap-2"><dt className="text-tube-quiet">Quality</dt><dd>{s.formats ?? 'Chosen when the fetch starts'}</dd></div>
            <div className="flex gap-2"><dt className="text-tube-quiet">Played here</dt><dd className="tabular-nums">{s.plays === 1 ? 'once' : `${s.plays} times`}</dd></div>
          </>
        )}
      </dl>
    </div>
  )
}

function UpNext({ current }: { current: string }) {
  const load = useLoad({ queryKey: keys.shuffle, queryFn: () => api.shuffle(UP_NEXT) })
  const byId = useChannelsById()
  return (
    <section aria-labelledby="up-next" className="grid content-start gap-3">
      <h2 id="up-next" className="text-tube-base font-medium">Up next</h2>
      <DataView error={trouble} state={load} skeleton={<RowsSkeleton rows={6} size="small" />} isEmpty={() => false} empty={null}>
        {vs => <ul aria-label="Up next" className="grid gap-3">{vs.filter(o => o.id !== current).map(o => <VideoRow key={o.id} v={o} channel={byId.get(o.channel_id)} size="small" />)}</ul>}
      </DataView>
    </section>
  )
}

export function WatchScreen() {
  const { id = '' } = useParams()
  const video = useLoad({
    queryKey: keys.video(id), queryFn: () => api.video(id),
    describeError: e => (e instanceof HttpError && e.status === 404 ? 'The library has no such video. It may have been removed since the link was made.' : describeHttpError(e)),
  })
  return (
    <div className="mx-auto flex max-w-screen-2xl flex-col gap-6 xl:flex-row">
      <div className="min-w-0 flex-1">
      <DataView error={trouble} state={video} isEmpty={() => false} empty={null} skeleton={<div aria-hidden className="grid gap-3 motion-safe:animate-pulse"><div className="aspect-video rounded-tube bg-tube-chip" /><div className="h-6 w-2/3 rounded-tube-sm bg-tube-chip" /></div>}>
        {v => <Stage key={v.id} v={v} />}
      </DataView>
      </div>
      <div className="shrink-0 xl:w-96"><UpNext current={id} /></div>
    </div>
  )
}

