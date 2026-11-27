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
//
// The play is kept with where it was started from (the list the link was in, from.tsx), and the player
// reports how much of it is seen as it goes (progress.ts), which is what Continue watching and later
// suggestions are made from. A video part watched lately picks up where it stopped, if that part is
// already on the server, with Start over beside the picture for a few seconds. Up next offers the part
// watched videos first, then a shuffle of the library. Every so many minutes of playing, a break may pause it
// and show another page over the picture until that page says it is done (break.tsx, Admin > Settings > Breaks);
// Break now under the player takes the next one at once, and counts down the playing time to it.
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { Button, DataView, describeHttpError, HttpError, type Load, type MediaHeading, type MediaSpanData, MediaPlayer, type PlayerWarningEvent, type SpanOutcome, useAsyncAction, useLoad, usePlayerWarnings } from 'strata-react'
import { api, describeError, keys, paths, withBase, type Channel, type Segment, type SegmentKind, type Segments, type Stream, type Video, type VideoDetail } from '../api'
import { attachStream, startingAt } from '../player'
import { decodes } from '../decodes'
import { Avatar, RowsSkeleton, VideoRow, useChannelsById } from './cards'
import { countFor, iplayerText, runningTime, viewsAndAge } from './format'
import { FromHere, fromState, useArrivedFrom } from './from'
import { useWatchReport } from './progress'
import { BreakFrame, useBreak } from './break'
import { reportMissing, useHidden } from './missing'
import { spanKindsOf, spansOf } from './skip'
import { trouble } from './Shown'

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

/** Where a play picks up: where the last one stopped, when the server says there is such a place and that part of the copy is here already
 *  (a copy being fetched again would make the player wait for it). 0 is the beginning. */
export function startAt(resume: number | null, s: Stream): number {
  if (!resume) return 0
  return s.complete || s.seconds >= resume + RESUME_MARGIN ? resume : 0
}

/** Seconds of the copy wanted past the place a play picks up, so it does not start on the last segment there is. */
export const RESUME_MARGIN = 10

/** The player: strata-react's `MediaPlayer` (its own controls on a desktop, the browser's on a touch screen), playing the stream through
 *  the HLS engine (player.ts), `growing` while the copy is still being fetched so playback that catches up waits and carries on, and
 *  saying a failure with Try again. The parts that can be skipped are its `spans` (skip.ts): drawn on the seek bar, an "ask" part offers
 *  Skip over the picture, an "auto" part is skipped (or muted) as it starts with Undo; a part skipped counts as seen. It reports how much
 *  is seen against `playId` (progress.ts), from the <video> inside it (MediaPlayer hands out its state, not its element). `start` is where
 *  it picks up, with "Picked up at" and Start over over the picture for a few seconds. `heading` is the title and channel the player draws
 *  across the top of the picture while it is paused or the pointer moves (strata-react #329). */
export function Player({ src, title, heading, segments, kinds, length, growing, playId, start, warning }: { src: string; title: string; heading?: MediaHeading; segments: Segment[]; kinds: SegmentKind[]; length: number | null; growing?: string; playId: number; start: number; warning?: PlayerWarningEvent }) {
  const box = useRef<HTMLDivElement>(null)
  // The <video> as a ref for the progress report, read when its effect runs (the player is in the page by then).
  const element = useMemo(() => ({ get current() { return box.current!.querySelector('video')! } }), [])
  const seen = useWatchReport(element, playId)
  const [from] = useState(start)                              // the first answer's: a later stream status does not move the picture
  const attach = useMemo(() => startingAt(attachStream, from), [from])
  const [picked, setPicked] = useState(from > 0)
  useEffect(() => {
    if (!picked) return
    const timer = setTimeout(() => setPicked(false), PICKED_MS)
    return () => clearTimeout(timer)
  }, [picked])
  const spans = useMemo(() => spansOf(segments, kinds), [segments, kinds])
  const spanKinds = useMemo(() => spanKindsOf(kinds), [kinds])
  const onSpan = useCallback((s: MediaSpanData, what: SpanOutcome) => { if (what === 'skipped') seen.mark(s.start, s.end) }, [seen])
  const breakLoad = useLoad({ queryKey: keys.break, queryFn: api.break })    // no break (not an error) until it answers, or if it fails
  const breakNow = breakLoad.status === 'ready' ? breakLoad.data : undefined
  const pause = useBreak(element, breakNow)
  return (
    <div ref={box}>
      <MediaPlayer kind="video" label={title} sources={[{ src, title, duration: length ?? undefined }]} attach={attach} autoPlay growing={growing !== undefined ? { status: growing } : undefined}
        spans={spans} spanKinds={spanKinds} onSpan={onSpan} warning={warning} heading={pause.due && breakNow?.url ? undefined : heading}
        status={breakNow?.url && !pause.due ? <Button variant="ghost" size="sm" onClick={pause.start}>Break now · next in <span className="tabular-nums">{runningTime(pause.left)}</span></Button> : undefined}
        overlay={media => pause.due && breakNow?.url ? <BreakFrame url={breakNow.url} limitMinutes={breakNow.limit_minutes} onDone={pause.end} /> : picked && (
          <p role="status" className="absolute bottom-3 left-3 flex items-center gap-2 rounded-overlay border border-border bg-background px-3 py-1 type-body-sm text-foreground shadow-overlay">
            Picked up at {runningTime(from)}
            <Button variant="ghost" size="sm" onClick={() => { setPicked(false); media.seek(0) }}>Start over</Button>
          </p>
        )} />
    </div>
  )
}

/** What the player draws over the picture: the title, and the channel with its picture, leading to the channel's page as a visit from
 *  this video (as the channel link under the player does). */
export function headingOf(v: VideoDetail, channel: Channel | undefined): MediaHeading {
  return { title: v.title, subtitle: v.channel ?? channel?.title, subtitleTo: `/channels/${encodeURIComponent(v.channel_id)}`, state: fromState({ source: 'watch', detail: v.id }), avatar: channel?.thumbnail ?? null }
}

/** Until the parts to skip are read: the same empty lists every render, so the player's spans stay put. */
const NONE: Segment[] = [], NO_KINDS: SegmentKind[] = []

/** How long "Picked up at" stays, with its Start over. */
export const PICKED_MS = 8000

/** Why the skippable parts are not known, or '' when they are (or are still being asked for): the read failed, or the server could not ask
 *  their source just now (it still sends what it had). */
export function skipTrouble(load: Load<Segments>): string {
  if (load.status === 'error') return `The parts to skip could not be read: ${load.message}`
  if (load.status === 'ready' && load.data.error) return `The parts to skip could not be looked up: ${load.data.error}`
  return ''
}

function Frame({ children }: { children: ReactNode }) {
  return <div className="grid aspect-video w-full place-items-center rounded-tube bg-tube-screen p-6 text-center text-tube-on-screen">{children}</div>
}

function Stage({ v }: { v: VideoDetail }) {
  const queryClient = useQueryClient()
  const byId = useChannelsById()
  const channel = byId.get(v.channel_id)
  const from = useArrivedFrom()
  // A Plex file is fetched as the browser can play it: the play says what it decodes, and the answer names the copy to stream (`copy`).
  const play = useLoad({ queryKey: keys.play(v.id), queryFn: async () => api.play(v.id, from, v.platform === 'plex' ? await decodes() : undefined), staleTime: Infinity, gcTime: 0, describeError })
  const copy = (play.status === 'ready' && play.data.copy) || v.id
  const stream = useLoad({
    queryKey: keys.stream(copy), queryFn: () => api.stream(copy), enabled: play.status === 'ready',
    refetchInterval: q => (settled(q.state.data) ? false : POLL_MS),
  })
  const again = useAsyncAction(async () => {
    await queryClient.resetQueries({ queryKey: keys.play(v.id) })
    await queryClient.invalidateQueries({ queryKey: keys.stream(copy) })
  }, { describeError })
  const skips = useLoad({ queryKey: keys.segments(v.id), queryFn: () => api.segments(v.id), staleTime: Infinity })   // what can be skipped: nothing (not an error) until it answers
  const skipMessage = skipTrouble(skips)
  const { warning, warn } = usePlayerWarnings()
  const skipReadFailed = skips.status === 'error'
  useEffect(() => {
    if (!skipMessage) return
    warn({
      title: skipMessage,
      description: 'The video plays as it is.',
      action: skipReadFailed ? { label: 'Try again', onPress: () => { void queryClient.refetchQueries({ queryKey: keys.segments(v.id), exact: true }) } } : undefined,
    })
  }, [skipMessage, skipReadFailed, warn, queryClient, v.id])
  const started = play.status === 'ready' ? play.data : undefined
  const s = !started ? undefined : stream.status === 'ready' ? stream.data : started
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
        <Player src={withBase(paths.playlist(copy))} title={v.title} heading={headingOf(v, channel)} segments={skips.status === 'ready' ? skips.data.segments : NONE} kinds={skips.status === 'ready' ? skips.data.categories : NO_KINDS} length={v.duration}
          growing={s.complete ? undefined : savedText(s, v.duration)} playId={started!.play_id} start={startAt(started!.resume, s)}
          warning={warning} />
      ) : (
        <Frame><p role="status" className="text-tube-base opacity-80">{waitingText(s)}</p></Frame>
      )}

      <h1 className="text-tube-lg font-bold">{v.title}</h1>
      <Link to={`/channels/${encodeURIComponent(v.channel_id)}`} state={fromState({ source: 'watch', detail: v.id })} className="flex w-fit items-center gap-3">
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

/** Up next: the part-watched videos first (not this one), then the shuffle, each video once. */
export function upNext(current: string, unfinished: Video[], shuffled: Video[]): Video[] {
  const seen = new Set([current])
  return [...unfinished, ...shuffled].filter(v => !seen.has(v.id) && (seen.add(v.id), true))
}

function UpNext({ current }: { current: string }) {
  const load = useLoad({ queryKey: keys.shuffle, queryFn: () => api.shuffle(UP_NEXT) })
  const unfinished = useLoad({ queryKey: keys.continueWatching, queryFn: () => api.continueWatching() })
  const byId = useChannelsById()
  const first = unfinished.status === 'ready' ? unfinished.data : []          // a failed read of these only leaves them out
  return (
    <section aria-labelledby="up-next" className="grid content-start gap-3">
      <h2 id="up-next" className="text-tube-base font-medium">Up next</h2>
      <FromHere source="up_next" detail={current}>
        <DataView error={trouble} state={load} skeleton={<RowsSkeleton rows={6} size="small" />} isEmpty={() => false} empty={null}>
          {vs => <ul aria-label="Up next" className="grid gap-3">{upNext(current, first, vs).map((o, i) => <VideoRow key={o.id} v={o} channel={byId.get(o.channel_id)} size="small" rank={i} />)}</ul>}
        </DataView>
      </FromHere>
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

