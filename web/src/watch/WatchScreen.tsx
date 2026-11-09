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
import { useQueryClient } from '@tanstack/react-query'
import Hls from 'hls.js'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { HttpError, describeHttpError, useAsyncAction, useLoad } from 'strata-react'
import { api, describeError, keys, paths, withBase, type Stream, type VideoDetail } from '../api'
import { attach, type HlsClass } from '../player'
import { Avatar, RowsSkeleton, VideoRow, useChannelsById } from './cards'
import { runningTime, videoCount, viewsAndAge } from './format'
import { Shown } from './Shown'

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

export function Player({ src, title }: { src: string; title: string }) {
  const ref = useRef<HTMLVideoElement>(null)
  const [problem, setProblem] = useState<string>()
  useEffect(() => attach(ref.current!, src, Hls as unknown as HlsClass, setProblem), [src])
  return (
    <div className="relative">
      <video ref={ref} controls autoPlay playsInline aria-label={title} className="aspect-video w-full rounded-tube bg-tube-screen" />
      {problem && <p role="alert" className="absolute inset-x-0 bottom-14 mx-auto w-fit max-w-11/12 rounded-tube-sm bg-tube-badge px-3 py-2 text-center text-tube-sm text-tube-on-screen">{problem}</p>}
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
  const s = play.status !== 'ready' ? undefined : stream.status === 'ready' ? stream.data : play.data

  return (
    <div className="grid content-start gap-3">
      {play.status === 'error' ? (
        <Frame><div role="alert" className="grid justify-items-center gap-2"><p className="text-tube-lg font-medium">This video cannot start now</p><p className="text-tube-sm opacity-80">{play.message}</p></div></Frame>
      ) : !s ? (
        <Frame><p role="status" className="text-tube-base opacity-80">Asking for the video…</p></Frame>
      ) : s.state === 'failed' ? (
        <Frame>
          <div className="grid justify-items-center gap-3">
            <p className="text-tube-lg font-medium">This video could not be fetched</p>
            <p className="text-tube-sm opacity-80">{s.error ?? 'The fetch stopped without saying why.'}</p>
            {/* Resetting the play puts the frame back to "Asking for the video…" at once, so the button needs no pending state. */}
            <button type="button" onClick={() => void again.run()} className="h-9 rounded-full bg-tube-on-screen px-4 text-tube-sm font-medium text-tube-screen hover:opacity-85">Fetch again</button>
          </div>
        </Frame>
      ) : s.playable ? (
        <Player src={withBase(paths.playlist(v.id))} title={v.title} />
      ) : (
        <Frame><p role="status" className="text-tube-base opacity-80">{waitingText(s)}</p></Frame>
      )}

      <h1 className="text-tube-lg font-bold">{v.title}</h1>
      <Link to={`/channels/${encodeURIComponent(v.channel_id)}`} className="flex w-fit items-center gap-3">
        <Avatar channel={channel} name={v.channel} size="size-10" />
        <span className="grid">
          <span className="text-tube-base font-medium">{v.channel ?? channel?.title ?? 'Channel'}</span>
          {channel && <span className="text-tube-xs text-tube-quiet">{videoCount(channel.videos)}</span>}
        </span>
      </Link>
      <dl className="grid gap-1 rounded-tube bg-tube-chip p-3 text-tube-sm">
        <div className="font-medium"><dt className="sr-only">Views and age</dt><dd>{viewsAndAge(v)}</dd></div>
        <div className="flex gap-2"><dt className="text-tube-quiet">Length</dt><dd className="tabular-nums">{runningTime(v.duration)}</dd></div>
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
      <Shown state={load} skeleton={<RowsSkeleton rows={6} size="small" />}>
        {vs => <ul aria-label="Up next" className="grid gap-3">{vs.filter(o => o.id !== current).map(o => <VideoRow key={o.id} v={o} channel={byId.get(o.channel_id)} size="small" />)}</ul>}
      </Shown>
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
      <Shown state={video} skeleton={<div aria-hidden className="grid gap-3 motion-safe:animate-pulse"><div className="aspect-video rounded-tube bg-tube-chip" /><div className="h-6 w-2/3 rounded-tube-sm bg-tube-chip" /></div>}>
        {v => <Stage key={v.id} v={v} />}
      </Shown>
      </div>
      <div className="shrink-0 xl:w-96"><UpNext current={id} /></div>
    </div>
  )
}

