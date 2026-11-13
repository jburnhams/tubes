// The one question: "What has this channel made?" A header (large picture, name, handle and how
// many videos) over a Videos tab and a grid of its videos, newest first, a page at a time. A channel
// the library no longer has (an old link) says so. An iPlayer programme reads the same, with its
// episodes under a heading for each series as the list reaches it (newest first, so the latest series leads).
// Each visit is recorded with where it came from (viewing.py): a query keyed on the visit (the location's key)
// with gcTime 0, as the watch page's play is, so React's double mount does not count it twice and coming back counts again.
import { HttpError, describeHttpError, useLoad } from 'strata-react'
import { useLocation, useParams } from 'react-router'
import { api, keys, type Channel, type Video } from '../api'
import { Avatar, GridSkeleton, More, VideoGrid } from './cards'
import { countFor } from './format'
import { FromHere, useArrivedFrom } from './from'
import { Nothing, Shown } from './Shown'
import { useVideos } from './useVideos'

/** Consecutive runs of episodes in the same series, in list order: [[series, episodes], ...]. */
export function bySeries(vs: Video[]): [string | null, Video[]][] {
  const runs: [string | null, Video[]][] = []
  for (const v of vs) {
    const s = v.series ?? null
    if (runs.length && runs[runs.length - 1][0] === s) runs[runs.length - 1][1].push(v)
    else runs.push([s, [v]])
  }
  return runs
}

function Episodes({ c, vs }: { c: Channel; vs: Video[] }) {
  const runs = bySeries(vs)
  if (runs.length === 1 && runs[0][0] === null) return <VideoGrid videos={vs} label={`Episodes of ${c.title}`} showChannel={false} />
  return (
    <div className="grid gap-10">
      {runs.map(([series, run], i) => (
        <section key={`${series}-${i}`} aria-label={series ?? 'Other episodes'} className="grid gap-4">
          <h2 className="text-tube-lg font-bold">{series ?? 'Other episodes'}</h2>
          <VideoGrid videos={run} label={`${series ?? 'Other episodes'} of ${c.title}`} showChannel={false} />
        </section>
      ))}
    </div>
  )
}

function Videos({ c }: { c: Channel }) {
  const list = useVideos({ channel: c.id })
  return (
    <Shown state={list} skeleton={<GridSkeleton cards={8} />} isEmpty={vs => vs.length === 0} empty={<Nothing title={c.platform === 'iplayer' ? 'No episodes to watch' : 'No videos yet'}>{c.platform === 'iplayer' ? 'iPlayer offers none of its episodes just now. New ones arrive with the next sync.' : 'The library has this channel but none of its videos. They arrive with its next sync.'}</Nothing>}>
      {vs => <>{c.platform === 'iplayer' ? <Episodes c={c} vs={vs} /> : <VideoGrid videos={vs} label={`Videos from ${c.title}`} showChannel={false} />}<More list={list} skeleton={<GridSkeleton cards={4} />} /></>}
    </Shown>
  )
}

/** Records the visit; draws nothing (a visit that could not be recorded is not the person's problem). */
function Visit({ id }: { id: string }) {
  const from = useArrivedFrom()
  const { key } = useLocation()
  useLoad({ queryKey: keys.channelView(id, key), queryFn: () => api.channelView(id, from), staleTime: Infinity, gcTime: 0, retry: false })
  return null
}

export function ChannelScreen() {
  const { id = '' } = useParams()
  const load = useLoad({
    queryKey: keys.channel(id), queryFn: () => api.channel(id),
    describeError: e => (e instanceof HttpError && e.status === 404 ? 'The library has no such channel. It may have been removed since the link was made.' : describeHttpError(e)),
  })
  return (
    <div className="mx-auto max-w-screen-2xl">
      <Shown state={load} skeleton={<div aria-hidden className="flex items-center gap-6 py-4 motion-safe:animate-pulse"><div className="size-32 rounded-full bg-tube-chip" /><div className="grid flex-1 gap-3"><div className="h-8 w-64 rounded-tube-sm bg-tube-chip" /><div className="h-4 w-48 rounded-tube-sm bg-tube-chip" /></div></div>}>
        {c => (
          <>
            <header className="flex items-center gap-6 py-4">
              <Avatar channel={c} size="size-20 sm:size-40 text-tube-xl" />
              <div className="grid gap-2">
                <h1 className="text-tube-lg font-bold sm:text-tube-xl">{c.title}</h1>
                <p className="text-tube-sm text-tube-quiet">{[c.handle, c.platform === 'iplayer' ? 'BBC iPlayer' : null, countFor(c)].filter(Boolean).join(' · ')}</p>
              </div>
            </header>
            <div className="mb-6 border-b border-tube-line">
              <span className="inline-block border-b-2 border-tube-ink px-3 pb-3 text-tube-base font-medium">{c.platform === 'iplayer' ? 'Episodes' : 'Videos'}</span>
            </div>
            <Visit id={c.id} />
            <FromHere source="channel" detail={c.id}><Videos c={c} /></FromHere>
          </>
        )}
      </Shown>
    </div>
  )
}
