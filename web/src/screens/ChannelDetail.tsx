// One channel, opened in place from any admin list that names channels (History, Suggestions,
// Library): the one question is "What is this channel to us, and what should the library do with
// it?". It answers with what the library holds of it, how much and how lately it was watched (per
// month over all the history, per account, the videos watched most), what YouTube says of it, and
// the options that apply to it here, the same on every page: Follow, Add watched videos, Dismiss
// or Restore the suggestion, Open in Tubes, Open on YouTube.
//
// It reads `GET /api/channels/{id}/overview` itself, so a list mounts it only for the row that is
// open (DataTable `expansion`, or a `Disclosure`), and a list of a hundred channels makes no
// requests until one is opened.
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { Button, DataView, EmptyState, LineChart, Metric, MetricStrip, Skeleton, Status, Thumbnail, format, useAsyncAction, useLoad } from 'strata-react'
import { api, describeError, keys, withBase, type Added, type ChannelOverview } from '../api'
import { fillPeriods, periodLabel } from './HistoryScreen'
import { describeFollowed } from './SuggestionsScreen'

/** The channel's place in the library, in a word. */
export function libraryState(o: ChannelOverview): { tone: 'success' | 'neutral' | 'info'; word: string } {
  if (!o.library) return { tone: 'neutral', word: 'Not in the library' }
  if (o.library.follow === false) return { tone: 'info', word: `${format.count(o.library.videos, 'video')} in the library, not followed` }
  return { tone: 'success', word: `Followed, ${format.count(o.library.videos, 'video')} here` }
}

/** How much and how lately it was watched, in a sentence. */
export function describeWatching(o: ChannelOverview): string {
  const h = o.history
  if (!h.watches) return 'Not in the watch history.'
  const accounts = h.sources.length > 1 ? `, across ${h.sources.map(s => `${s.source} (${format.integer(s.watches)})`).join(' and ')}` : ''
  return `Watched ${format.count(h.watches, 'time')} (${format.count(h.videos, 'video')}) from ${format.date(h.first!)} to ${format.date(h.last!)}${accounts}.`
}

/** Where the channel lives outside Tubes: its iPlayer programme page, or its YouTube channel. */
export function elsewhere(o: Pick<ChannelOverview, 'channel_id' | 'library'>): { href: string; label: string } {
  const category = o.channel_id.startsWith('iplayer-') ? o.channel_id.slice('iplayer-'.length) : null      // a followed category (iplayer-films)
  return o.library?.platform === 'iplayer'
    ? { href: category ? `https://www.bbc.co.uk/iplayer/categories/${encodeURIComponent(category)}/featured` : `https://www.bbc.co.uk/iplayer/episodes/${encodeURIComponent(o.channel_id)}`, label: 'Open on iPlayer' }
    : { href: `https://www.youtube.com/channel/${encodeURIComponent(o.channel_id)}`, label: 'Open on YouTube' }
}

/** Its suggestion group and YouTube's topics for it, or '' when it has neither. */
export function placeLine(o: Pick<ChannelOverview, 'group' | 'suggestion'>): string {
  return [o.group ? `Group: ${o.group.name}` : '', o.suggestion?.topics.join(', ') ?? ''].filter(Boolean).join(' · ')
}

/** `dismiss`: how the page that opened the panel dismisses (or restores) the suggestion, when that removes the row the panel sits in.
 *  The Suggestions list passes its own, which goes through `useUndoable`; elsewhere the panel stays open and offers Restore at once. */
export function ChannelDetail({ id, dismiss }: { id: string; dismiss?: () => void }) {
  const load = useLoad({ queryKey: keys.overview(id), queryFn: () => api.overview(id) })
  return (
    <DataView state={load} isEmpty={() => false} skeleton={<DetailSkeleton />} empty={<EmptyState title="Nothing known">Nothing is known of this channel.</EmptyState>}>
      {o => <Detail o={o} onDismiss={dismiss} />}
    </DataView>
  )
}

function Detail({ o, onDismiss }: { o: ChannelOverview; onDismiss?: () => void }) {
  const queryClient = useQueryClient()
  const [said, setSaid] = useState<string>()
  const reread = async () => { for (const queryKey of [keys.suggestions, keys.channels, keys.library, keys.videos]) await queryClient.invalidateQueries({ queryKey }) }
  const follow = useAsyncAction(async () => {
    const r = await api.add(o.channel_id)                                   // a channel's id adds the channel, followed, and syncs it
    const sync = (r as Extract<Added, { kind: 'channel' }>).sync
    queryClient.setQueryData(keys.sync, sync)                               // the Library page polls a running sync it knows of
    setSaid(describeFollowed(o.title, sync)); await reread()
  }, { describeError })
  const addWatched = useAsyncAction(async () => {
    const r = await api.addWatched(o.channel_id)
    setSaid(`Added ${format.count(r.added, 'video')} of ${o.title} to the library.`); await reread()
  }, { describeError })
  const dismiss = useAsyncAction(async (dismissed: boolean) => {
    await api.dismiss(o.channel_id, dismissed)
    setSaid(dismissed ? `Dismissed ${o.title} from the suggestions.` : `${o.title} is back in the suggestions.`); await reread()
  }, { describeError })

  const h = o.history
  const periods = fillPeriods({ by: 'month', periods: h.periods })
  const state = libraryState(o)
  const followed = o.library?.follow !== false && !!o.library
  const failure = [follow, addWatched, dismiss].find(a => a.phase === 'error')
  const s = o.suggestion

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start gap-3">
        <Thumbnail src={o.thumbnail} alt="" missing="None" className="w-14 shrink-0 rounded-full" />
        <div className="grid min-w-0 flex-1 gap-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="type-body font-medium">{o.title}</span>
            {o.handle && <span className="type-caption text-muted-foreground">{o.handle}</span>}
            <Status tone={state.tone}>{state.word}</Status>
            {s?.made_for_kids && <Status tone="neutral">Made for kids</Status>}
            {s?.dismissed && <Status tone="neutral">Dismissed</Status>}
          </p>
          <p className="type-body-sm text-muted-foreground">{describeWatching(o)}</p>
          {placeLine(o) && <p className="type-caption text-muted-foreground">{placeLine(o)}</p>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {o.configured && !followed && <Button size="sm" variant="outline" disabled={follow.phase === 'pending'} onClick={() => void follow.run()}>Follow</Button>}
        {o.configured && !followed && h.watches > 0 && <Button size="sm" variant="outline" disabled={addWatched.phase === 'pending'} onClick={() => void addWatched.run()}>Add watched videos</Button>}
        {s && !followed && <Button size="sm" variant="outline" disabled={dismiss.phase === 'pending'} onClick={() => (onDismiss ? onDismiss() : void dismiss.run(!s.dismissed))}>{s.dismissed ? 'Restore suggestion' : 'Dismiss suggestion'}</Button>}
        {o.library && <Link to={`/channels/${encodeURIComponent(o.channel_id)}`} className="type-body-sm underline-offset-2 hover:underline">Open in Tubes</Link>}
        <a href={withBase(elsewhere(o).href)} target="_blank" rel="noreferrer" className="type-body-sm underline-offset-2 hover:underline">{elsewhere(o).label}</a>
      </div>
      {failure && <p role="alert" className="type-body-sm text-danger">{failure.error}</p>}
      {said && !failure && <p role="status" className="type-body-sm">{said}</p>}

      <MetricStrip label={`${o.title} in numbers`}>
        <Metric label="Watches" value={format.integer(h.watches)} />
        <Metric label="Videos watched" value={format.integer(h.videos)} />
        <Metric label="On YouTube" value={format.integer(o.library?.total_videos ?? s?.total_videos ?? 0)} unit="videos" />
        <Metric label="Subscribers" value={(o.library?.subscribers ?? s?.subscribers) == null ? '–' : format.integer((o.library?.subscribers ?? s?.subscribers)!)} />
      </MetricStrip>

      {periods.length > 1 && (
        <LineChart
          label={`Watches of ${o.title} per month`}
          series={periods.map((p, i) => ({ x: i, y: p.watches }))}
          seriesLabel="Watches"
          formatX={x => periodLabel(periods[Math.round(x)].period, 'month')}
          formatY={y => format.integer(y)}
          xTicks={periods.map((_, i) => i)}
          height={160}
        />
      )}

      {h.videos_top.length > 0 && (
        <section aria-label={`Videos of ${o.title} watched most`} className="grid gap-1">
          <h3 className="type-label text-muted-foreground">Watched most</h3>
          <ol className="grid gap-1">
            {h.videos_top.map(v => { const name = v.title ?? 'A video no longer on YouTube'; return (
              <li key={v.video_id} className="flex items-baseline justify-between gap-3 type-body-sm">
                {v.in_library ? <Link to={`/watch/${encodeURIComponent(v.video_id)}`} className="min-w-0 truncate hover:underline">{name}</Link>
                  : <a href={withBase(`https://www.youtube.com/watch?v=${encodeURIComponent(v.video_id)}`)} target="_blank" rel="noreferrer" className="min-w-0 truncate hover:underline">{name}</a>}
                <span className="shrink-0 tabular-nums text-muted-foreground">{format.count(v.watches, 'time')}</span>
              </li>
            ) })}
          </ol>
        </section>
      )}
    </div>
  )
}

/** Mirrors the panel: picture and lines, the options, the figures, a chart. */
function DetailSkeleton() {
  return (
    <div className="grid gap-4" aria-hidden>
      <div className="flex items-center gap-3"><Skeleton className="size-14 rounded-full" /><div className="grid flex-1 gap-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-3 w-2/3" /></div></div>
      <Skeleton className="h-8 w-80" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  )
}
