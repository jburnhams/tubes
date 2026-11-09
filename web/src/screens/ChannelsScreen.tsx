// The one question: "Which channels are in the library?" A grid of channels by name, each one link
// to its videos, with how many there are and how recent the newest is. Channels are added and
// removed in the library itself, not here, so the empty state says where.
import { Link } from 'react-router'
import { DataView, EmptyState, PageHeader, Skeleton, Thumbnail, ThumbnailSkeleton, format, useLoad } from 'strata-react'
import { api, keys, type Channel } from '../api'

/** The page's finding. */
export function describeChannels(cs: Channel[]): string {
  const total = cs.reduce((n, c) => n + c.videos, 0)
  const latest = cs.map(c => c.latest).filter((d): d is string => !!d).sort().at(-1)
  return `${format.count(cs.length, 'channel')} with ${format.count(total, 'video')}${latest ? `; the newest is from ${format.date(latest)}` : ''}.`
}

function ChannelCard({ c }: { c: Channel }) {
  return (
    <li>
      <Link to={`/channels/${encodeURIComponent(c.id)}`} className="grid gap-2 rounded-surface transition-state hover:text-primary">
        <Thumbnail src={c.thumbnail} alt="" missing="No picture" aspect={1} eager className="w-full" />
        <span className="type-body font-medium">{c.title}</span>
        <span className="type-body-sm text-muted-foreground tabular-nums">{format.count(c.videos, 'video')}{c.latest ? ` · newest ${format.date(c.latest)}` : ''}</span>
      </Link>
    </li>
  )
}

const grid = 'grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-5'

function ChannelsSkeleton() {
  return (
    <div className={grid} aria-hidden>
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} className="grid gap-2"><ThumbnailSkeleton aspect={1} className="w-full" /><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3.5 w-1/2" /></div>
      ))}
    </div>
  )
}

export function ChannelsScreen() {
  const load = useLoad({ queryKey: keys.channels, queryFn: api.channels })
  return (
    <>
      <PageHeader title="Channels" scope="By name" finding={load.status === 'ready' && load.data.length ? { text: describeChannels(load.data) } : undefined} />
      <DataView
        state={load}
        isEmpty={cs => cs.length === 0}
        skeleton={<ChannelsSkeleton />}
        empty={<EmptyState title="No channels yet">Channels are added in the library itself. Once they are there, a sync on the System page copies them here.</EmptyState>}
      >
        {cs => <ul aria-label="Channels" className={grid}>{cs.map(c => <ChannelCard key={c.id} c={c} />)}</ul>}
      </DataView>
    </>
  )
}
