// The one question: "Can I watch this now?" Opening the page is the play: it records the play and
// starts the fetch unless the video is already in the cache (POST /play). The server writes the copy
// as HLS while it downloads, so the player starts as soon as the first few seconds are on disk
// (`playable`), usually two or three seconds, and follows the copy as it grows. Until then the
// frame says what is happening; if the fetch fails it says why, with Fetch again.
//
// The play is a useLoad keyed on the video with gcTime 0: a query, not an effect, so React's
// double-mount in development does not record two plays, and leaving and coming back records a new
// one. The stream status is polled each second until the copy is complete or has failed.
import { useQueryClient } from '@tanstack/react-query'
import Hls from 'hls.js'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { AsyncButton, DataView, EmptyState, HttpError, PageHeader, Skeleton, Status, describeHttpError, format, useAsyncAction, useLoad } from 'strata-react'
import { api, describeError, keys, paths, runningTime, withBase, type Stream, type VideoDetail } from '../api'
import { attach, type HlsClass } from '../player'

/** How often the copy's progress is read while it is still arriving. */
export const POLL_MS = 1000

/** Polling stops once the copy is whole or the fetch has failed. */
export const settled = (s: Stream | undefined) => !!s && (s.complete || s.state === 'failed')

/** What the frame says while the first seconds are on their way. */
export function waitingText(s: Stream): string {
  if (s.state === 'none') return 'Asking for the video…'
  return s.formats ? `Fetching ${s.formats}. It starts in a moment.` : 'Finding the best copy to fetch…'
}

/** How much of the video is in the cache, in words. */
export function savedText(s: Stream, duration: number | null): string {
  if (s.complete) return 'All of it, kept in the cache'
  if (s.state === 'failed' || s.state === 'none') return 'None'
  return duration ? `${runningTime(s.seconds)} of ${runningTime(duration)} so far` : `${runningTime(s.seconds)} so far`
}

export function Player({ src, title }: { src: string; title: string }) {
  const ref = useRef<HTMLVideoElement>(null)
  const [problem, setProblem] = useState<string>()
  useEffect(() => attach(ref.current!, src, Hls as unknown as HlsClass, setProblem), [src])
  return (
    <div className="grid gap-2">
      <video ref={ref} controls autoPlay playsInline aria-label={title} className="aspect-video w-full rounded-surface bg-muted" />
      {problem && <p role="alert" className="type-body-sm text-danger">{problem}</p>}
    </div>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  return <div className="grid aspect-video w-full place-items-center rounded-surface bg-muted p-6 text-center">{children}</div>
}

function Stage({ v }: { v: VideoDetail }) {
  const queryClient = useQueryClient()
  const play = useLoad({ queryKey: keys.play(v.id), queryFn: () => api.play(v.id), staleTime: Infinity, gcTime: 0, describeError })
  const stream = useLoad({
    queryKey: keys.stream(v.id), queryFn: () => api.stream(v.id), enabled: play.status === 'ready',
    refetchInterval: q => (settled(q.state.data) ? false : POLL_MS),
  })
  const again = useAsyncAction(async () => {
    await queryClient.resetQueries({ queryKey: keys.play(v.id) })
    await queryClient.invalidateQueries({ queryKey: keys.stream(v.id) })
  }, { describeError })

  return (
    <DataView state={play} isEmpty={() => false} skeleton={<Skeleton className="aspect-video w-full" />} empty={null}>
      {first => {
        const s = stream.status === 'ready' ? stream.data : first
        return (
          <div className="grid gap-6">
            {s.state === 'failed' ? (
              <Frame>
                <EmptyState title="This video could not be fetched" action={<AsyncButton variant="default" phase={again.phase} error={again.error} labels={{ idle: 'Fetch again', pending: 'Asking…', done: 'Asked' }} onClick={() => void again.run()} />}>
                  {s.error ?? 'The fetch stopped without saying why.'}
                </EmptyState>
              </Frame>
            ) : s.playable ? (
              <Player src={withBase(paths.playlist(v.id))} title={v.title} />
            ) : (
              <Frame><p role="status" className="type-body text-muted-foreground">{waitingText(s)}</p></Frame>
            )}
            <dl className="grid max-w-xl gap-2 type-body-sm">
              {([
                ['Length', <span className="tabular-nums">{runningTime(v.duration)}</span>],
                ['Published', format.date(v.published)],
                ['Copy', <span className="flex flex-wrap items-center gap-2"><CopyWord s={s} /><span className="tabular-nums">{savedText(s, v.duration)}</span></span>],
                ['Quality', s.formats ?? 'Chosen when the fetch starts'],
                ['Plays', <span className="tabular-nums">{format.integer(s.plays)}</span>],
              ] as const).map(([term, value]) => (
                <div key={term} className="flex gap-6">
                  <dt className="w-24 shrink-0 text-muted-foreground">{term}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        )
      }}
    </DataView>
  )
}

function CopyWord({ s }: { s: Stream }) {
  if (s.complete) return <Status tone="success">Saved</Status>
  if (s.state === 'failed') return <Status tone="danger">Failed</Status>
  return <Status tone="info">Fetching</Status>
}

export function WatchScreen() {
  const { id = '' } = useParams()
  const video = useLoad({
    queryKey: keys.video(id), queryFn: () => api.video(id),
    describeError: e => (e instanceof HttpError && e.status === 404 ? 'The library has no such video. It may have been removed since the link was made.' : describeHttpError(e)),
  })
  return (
    <DataView
      state={video}
      isEmpty={() => false}
      skeleton={<div className="grid gap-6" aria-hidden><Skeleton className="h-9 w-2/3" /><Skeleton className="aspect-video w-full" /></div>}
      empty={null}
    >
      {v => (
        <>
          <PageHeader title={v.title} scope={<Link to={`/channels/${encodeURIComponent(v.channel_id)}`} className="underline-offset-4 hover:underline">{v.channel ?? 'Channel'}</Link>} />
          <Stage key={v.id} v={v} />
        </>
      )}
    </DataView>
  )
}
