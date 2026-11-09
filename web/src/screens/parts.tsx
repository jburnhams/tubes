// Pieces several screens draw the same way: a video as a card (in a grid) or a row (in a list),
// their loading shapes, the word for a video's copy, and the search form. A video is always one
// link to its watch page, named by its title, so a screen reader hears one stop per video.
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button, Field, Input, Skeleton, Status, Thumbnail, ThumbnailSkeleton, format } from 'strata-react'
import { runningTime, type CacheState, type Video } from '../api'

/** A copy's state as a word: whether the video plays at once from the cache. None for no copy. */
export function CopyStatus({ state }: { state: CacheState | null }) {
  if (state === 'ready') return <Status tone="success">Saved</Status>
  if (state === 'fetching') return <Status tone="info">Fetching</Status>
  if (state === 'failed') return <Status tone="warning">Failed last time</Status>
  return null
}

/** "Workshop Notes · 12:04 · 3 Jan 2026": channel, running time, date. */
export function videoFacts(v: Video, withChannel = true): string {
  return [withChannel ? v.channel : null, runningTime(v.duration), format.date(v.published)].filter(Boolean).join(' · ')
}

export function VideoCard({ v, eager = false }: { v: Video; eager?: boolean }) {
  return (
    <li className="grid content-start gap-2">
      <Link to={`/watch/${encodeURIComponent(v.id)}`} className="grid gap-2 rounded-surface transition-state hover:text-primary">
        <Thumbnail src={v.thumbnail} alt="" missing="No picture" aspect="16/9" eager={eager} className="w-full" />
        <span className="line-clamp-2 type-body font-medium">{v.title}</span>
      </Link>
      <span className="flex flex-wrap items-center gap-2 type-body-sm text-muted-foreground">
        <span className="tabular-nums">{videoFacts(v)}</span>
        <CopyStatus state={v.cache_state} />
      </span>
    </li>
  )
}

export function VideoGrid({ videos, label }: { videos: Video[]; label: string }) {
  return (
    <ul aria-label={label} className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {videos.map((v, i) => <VideoCard key={v.id} v={v} eager={i < 8} />)}
    </ul>
  )
}

/** Mirrors VideoGrid: the same columns and card shape. */
export function GridSkeleton({ cards = 8 }: { cards?: number }) {
  return (
    <div className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-hidden>
      {Array.from({ length: cards }, (_, i) => (
        <div key={i} className="grid gap-2">
          <ThumbnailSkeleton aspect="16/9" className="w-full" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-3.5 w-1/2" />
        </div>
      ))}
    </div>
  )
}

/** A video as a list row, for the long, paged lists (a channel, search results). */
export function VideoRow({ v, withChannel = true }: { v: Video; withChannel?: boolean }) {
  return (
    <div className="flex items-start gap-4 py-2">
      <Link to={`/watch/${encodeURIComponent(v.id)}`} className="flex min-w-0 flex-1 items-start gap-4 transition-state hover:text-primary">
        <Thumbnail src={v.thumbnail} alt="" missing="No picture" aspect="16/9" className="w-32 shrink-0 sm:w-40" />
        <span className="grid min-w-0 gap-1">
          <span className="line-clamp-2 type-body font-medium">{v.title}</span>
          <span className="type-body-sm text-muted-foreground tabular-nums">{videoFacts(v, withChannel)}</span>
        </span>
      </Link>
      <span className="hidden shrink-0 sm:block"><CopyStatus state={v.cache_state} /></span>
    </div>
  )
}

/** Mirrors VideoRow. */
export function RowsSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="grid" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-start gap-4 py-2">
          <ThumbnailSkeleton aspect="16/9" className="w-32 shrink-0 sm:w-40" />
          <div className="grid flex-1 gap-2 pt-1">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3.5 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Search the library's titles: goes to /search?q=, so results can be linked and reloaded. */
export function SearchForm({ initial = '' }: { initial?: string }) {
  const [q, setQ] = useState(initial)
  const navigate = useNavigate()
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (q.trim()) navigate(`/search?${new URLSearchParams({ q: q.trim() })}`)
  }
  return (
    <form role="search" onSubmit={onSubmit} className="flex max-w-xl items-end gap-3">
      <Field label="Search titles" className="flex-1">
        <Input type="search" value={q} onChange={e => setQ(e.target.value)} autoComplete="off" />
      </Field>
      <Button type="submit" variant="default">Search</Button>
    </form>
  )
}
