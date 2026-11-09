// Videos and channels drawn the way the old Tubes app drew them: a rounded 16:9 thumbnail with the
// running time in its corner, then the channel's round picture beside a bold two-line title, the
// channel's name and "views · age". A video is one link to its watch page, named by its title: the picture
// and avatar are links too, for the mouse, but hidden from the keyboard and screen readers so each video is said once.
import { useEffect, useRef, type ReactNode } from 'react'
import { Link } from 'react-router'
import { useLoad, type InfiniteLoad } from 'strata-react'
import { api, keys, type Channel, type Video } from '../api'
import { runningTime, viewsAndAge } from './format'
import { Pill } from './Shown'

/** The channels, by id, from the one shared read (the rail reads the same query). */
export function useChannelsById(): Map<string, Channel> {
  const load = useLoad({ queryKey: keys.channels, queryFn: api.channels })
  return new Map(load.status === 'ready' ? load.data.map(c => [c.id, c]) : [])
}

/** A channel's round picture, or its first letter on grey when it has none. */
export function Avatar({ channel, name, size = 'size-9' }: { channel?: Channel; name?: string | null; size?: string }) {
  const title = channel?.title ?? name ?? '?'
  return channel?.thumbnail
    ? <img src={channel.thumbnail} alt="" className={`${size} shrink-0 rounded-full bg-tube-chip object-cover`} />
    : <span aria-hidden className={`${size} grid shrink-0 place-items-center rounded-full bg-tube-chip font-medium text-tube-quiet`}>{title.slice(0, 1).toUpperCase()}</span>
}

const SAVED: Record<string, string> = { ready: 'Saved', fetching: 'Fetching' }

/** The thumbnail with its running time, and a corner label when a copy is on this server. */
export function Picture({ v, className = '' }: { v: Video; className?: string }) {
  const saved = v.cache_state ? SAVED[v.cache_state] : undefined
  return (
    <span className={`relative block aspect-video overflow-hidden rounded-tube bg-tube-chip ${className}`}>
      {v.thumbnail && <img src={v.thumbnail} alt="" className="size-full object-cover" />}
      {saved && <span className="absolute top-2 left-2 rounded-tube-sm bg-tube-badge px-1.5 py-0.5 text-tube-xs font-medium text-tube-on-screen">{saved}</span>}
      {v.duration ? <span className="absolute right-2 bottom-2 rounded-tube-sm bg-tube-badge px-1 text-tube-xs font-medium text-tube-on-screen tabular-nums">{runningTime(v.duration)}</span> : null}
    </span>
  )
}

const watchPath = (v: Video) => `/watch/${encodeURIComponent(v.id)}`

export function VideoCard({ v, channel, showChannel = true }: { v: Video; channel?: Channel; showChannel?: boolean }) {
  return (
    <li className="grid content-start gap-3">
      <Link to={watchPath(v)} tabIndex={-1} aria-hidden><Picture v={v} /></Link>
      <div className="flex gap-3">
        {showChannel && <Link to={`/channels/${encodeURIComponent(v.channel_id)}`} tabIndex={-1} aria-hidden><Avatar channel={channel} name={v.channel} /></Link>}
        <div className="grid min-w-0 content-start gap-1">
          <Link to={watchPath(v)} className="line-clamp-2 text-tube-base font-medium text-tube-ink">{v.title}</Link>
          {showChannel && <Link to={`/channels/${encodeURIComponent(v.channel_id)}`} className="text-tube-sm text-tube-quiet hover:text-tube-ink">{v.channel ?? channel?.title ?? 'Channel'}</Link>}
          <span className="text-tube-sm text-tube-quiet">{viewsAndAge(v)}</span>
        </div>
      </div>
    </li>
  )
}

export const gridClass = 'grid grid-cols-1 gap-x-4 gap-y-10 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4'

export function VideoGrid({ videos, label, showChannel = true }: { videos: Video[]; label: string; showChannel?: boolean }) {
  const byId = useChannelsById()
  return <ul aria-label={label} className={gridClass}>{videos.map(v => <VideoCard key={v.id} v={v} channel={byId.get(v.channel_id)} showChannel={showChannel} />)}</ul>
}

/** Mirrors VideoGrid: grey thumbnails, a grey disc and two grey lines. */
export function GridSkeleton({ cards = 12 }: { cards?: number }) {
  return (
    <div aria-hidden className={gridClass}>
      {Array.from({ length: cards }, (_, i) => (
        <div key={i} className="grid gap-3 motion-safe:animate-pulse">
          <div className="aspect-video rounded-tube bg-tube-chip" />
          <div className="flex gap-3"><div className="size-9 rounded-full bg-tube-chip" /><div className="grid flex-1 gap-2"><div className="h-4 w-11/12 rounded-tube-sm bg-tube-chip" /><div className="h-3 w-1/2 rounded-tube-sm bg-tube-chip" /></div></div>
        </div>
      ))}
    </div>
  )
}

/** A video as a wide row: search results and Up next. */
export function VideoRow({ v, channel, size = 'large' }: { v: Video; channel?: Channel; size?: 'large' | 'small' }) {
  const large = size === 'large'
  return (
    <li>
      {/* A large row stacks on a phone, where a picture beside the title leaves the title no room. */}
      <Link to={watchPath(v)} className={`flex items-start ${large ? 'flex-col gap-3 sm:flex-row sm:gap-4' : 'gap-2'}`}>
        <Picture v={v} className={large ? 'w-full shrink-0 sm:w-80 lg:w-96' : 'w-40 shrink-0'} />
        <span className={`grid min-w-0 content-start ${large ? 'gap-2 pt-1' : 'gap-1'}`}>
          <span className={`line-clamp-2 font-medium text-tube-ink ${large ? 'text-tube-lg' : 'text-tube-sm'}`}>{v.title}</span>
          {large && <span className="text-tube-xs text-tube-quiet">{viewsAndAge(v)}</span>}
          <span className="flex items-center gap-2 text-tube-xs text-tube-quiet">{large && <Avatar channel={channel} name={v.channel} size="size-6" />}{v.channel ?? channel?.title}</span>
          {!large && <span className="text-tube-xs text-tube-quiet">{viewsAndAge(v)}</span>}
        </span>
      </Link>
    </li>
  )
}

export function RowsSkeleton({ rows = 4, size = 'large' }: { rows?: number; size?: 'large' | 'small' }) {
  return (
    <div aria-hidden className="grid gap-4">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={`flex items-start motion-safe:animate-pulse ${size === 'large' ? 'flex-col gap-3 sm:flex-row sm:gap-4' : 'gap-2'}`}>
          <div className={`aspect-video shrink-0 rounded-tube bg-tube-chip ${size === 'large' ? 'w-full sm:w-80 lg:w-96' : 'w-40'}`} />
          <div className="grid w-full flex-1 content-start gap-2 pt-1"><div className="h-4 w-4/5 rounded-tube-sm bg-tube-chip" /><div className="h-3 w-1/3 rounded-tube-sm bg-tube-chip" /></div>
        </div>
      ))}
    </div>
  )
}

/** After a paged list: asks for the next page as it scrolls into view (as video sites do), says why a page failed with Try again, and
 *  keeps a Show more button for whoever cannot scroll. Nothing after the last page. */
export function More({ list, skeleton }: { list: InfiniteLoad<Video>; skeleton: ReactNode }) {
  const { hasMore, loadingMore, error, loadMore } = list.more
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // Without IntersectionObserver (jsdom, a very old browser) Show more still works.
    if (typeof IntersectionObserver === 'undefined' || !hasMore || error) return
    const seen = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) loadMore() }, { rootMargin: '600px' })
    seen.observe(ref.current!)
    return () => seen.disconnect()
  }, [hasMore, error, loadMore])
  if (!hasMore) return null
  return (
    <div ref={ref} className="mt-10 grid gap-6">
      {loadingMore ? skeleton : error ? (
        <div role="alert" className="flex flex-wrap items-center justify-center gap-4 text-tube-sm text-tube-ink">{error}<Pill onClick={loadMore}>Try again</Pill></div>
      ) : (
        <div className="flex justify-center"><Pill onClick={loadMore}>Show more</Pill></div>
      )}
    </div>
  )
}
