// The one question: "What has this channel made?" A header (large picture, name, handle and how
// many videos) over a Videos tab and a grid of its videos, newest first, a page at a time. A channel
// the library no longer has (an old link) says so.
import { HttpError, describeHttpError, useLoad } from 'strata-react'
import { useParams } from 'react-router'
import { api, keys, type Channel } from '../api'
import { Avatar, GridSkeleton, More, VideoGrid } from './cards'
import { videoCount } from './format'
import { Nothing, Shown } from './Shown'
import { useVideos } from './useVideos'

function Videos({ c }: { c: Channel }) {
  const list = useVideos({ channel: c.id })
  return (
    <Shown state={list} skeleton={<GridSkeleton cards={8} />} isEmpty={vs => vs.length === 0} empty={<Nothing title="No videos yet">The library has this channel but none of its videos. They arrive with its next sync.</Nothing>}>
      {vs => <><VideoGrid videos={vs} label={`Videos from ${c.title}`} showChannel={false} /><More list={list} skeleton={<GridSkeleton cards={4} />} /></>}
    </Shown>
  )
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
                <p className="text-tube-sm text-tube-quiet">{[c.handle, videoCount(c.videos)].filter(Boolean).join(' · ')}</p>
              </div>
            </header>
            <div className="mb-6 border-b border-tube-line">
              <span className="inline-block border-b-2 border-tube-ink px-3 pb-3 text-tube-base font-medium">Videos</span>
            </div>
            <Videos c={c} />
          </>
        )}
      </Shown>
    </div>
  )
}
