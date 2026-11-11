// The one question: "What has been watched, and when?" The finding answers it for the chosen
// timeframe in a sentence (how many watches of how many videos from how many channels, and the
// most watched channel), or says where a history comes from. Then, in the order a person asks
// next: how watching rose and fell over the timeframe (a line of watches per day, or per month
// over longer spans), the channels watched most, and the videos watched most.
//
// The timeframe and the account live in the URL (?range=12m&source=main), so a view can be linked.
// The history is the one the Suggestions page is made from: imported from Google Takeout, or read
// from a history database on the server.
import { Link, useSearchParams } from 'react-router'
import { DataTable, DataView, EmptyState, Field, LineChart, NativeSelect, PageHeader, Skeleton, Status, TableSkeleton, format, useLoad, type Column } from 'strata-react'
import { api, keys, withBase, type HistoryFilter, type HistorySource, type HistoryStats } from '../api'

type TopChannel = HistoryStats['channels_top'][number]
type TopVideo = HistoryStats['videos_top'][number]

const DAY = 86_400_000

/** A timeframe from the URL as the server's start and end, and in words. `30d`, `12m` and `all`, or a year such as `2024`. */
export function rangeOf(value: string | null, now = Date.now()): { start?: string; end?: string; words: string } {
  const iso = (t: number) => new Date(t).toISOString().replace('.000Z', '+00:00')
  if (value === '30d') return { start: iso(now - 30 * DAY), words: 'in the last 30 days' }
  if (value === 'all') return { words: 'in all the history' }
  if (value && /^\d{4}$/.test(value)) return { start: `${value}-01-01T00:00:00+00:00`, end: `${Number(value) + 1}-01-01T00:00:00+00:00`, words: `in ${value}` }
  return { start: iso(now - 365 * DAY), words: 'in the last 12 months' }
}

/** The timeframes to choose from: the fixed ones, then every year the histories cover, newest first. */
export function rangeChoices(sources: HistorySource[]): { value: string; label: string }[] {
  const years = sources.flatMap(s => [Number(s.first.slice(0, 4)), Number(s.last.slice(0, 4))])
  const out = [{ value: '12m', label: 'Last 12 months' }, { value: '30d', label: 'Last 30 days' }, { value: 'all', label: 'All time' }]
  if (!years.length) return out
  for (let y = Math.max(...years); y >= Math.min(...years); y--) out.push({ value: String(y), label: String(y) })
  return out
}

/** A channel's name, or its id when the history never gave one. */
export const channelName = (c: Pick<TopChannel, 'title' | 'channel_id'>) => c.title ?? c.channel_id

/** The page's finding. */
export function describeHistory(h: HistoryStats, words: string): string {
  if (!h.sources.length) return 'No watch history yet. Bring one in on the Suggestions page (a Google Takeout file), or set a history database on the server.'
  if (!h.watches) return `Nothing was watched ${words}.`
  const top = h.channels_top[0]
  const most = top ? ` Most watched: ${channelName(top)}, ${format.count(top.watches, 'time')}.` : ''
  return `${format.count(h.watches, 'watch', 'watches')} of ${format.count(h.videos, 'video')} from ${format.count(h.channels, 'channel')} ${words}.${most}`
}

/** A period's label on the chart: a month (`Mar 2026`) or a day (`3 Mar`). */
export function periodLabel(period: string, by: HistoryStats['by']): string {
  const d = new Date(`${by === 'month' ? `${period}-01` : period}T00:00:00Z`)
  return by === 'month' ? d.toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' }) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

/** Gaps in the periods filled with nothing watched, so the line falls to zero rather than jumping over a quiet month. */
export function fillPeriods(h: Pick<HistoryStats, 'periods' | 'by'>): { period: string; watches: number }[] {
  if (h.periods.length < 2) return h.periods
  const have = new Map(h.periods.map(p => [p.period, p.watches]))
  const out: { period: string; watches: number }[] = []
  const step = (p: string) => {
    const d = new Date(`${h.by === 'month' ? `${p}-01` : p}T00:00:00Z`)
    if (h.by === 'month') d.setUTCMonth(d.getUTCMonth() + 1); else d.setUTCDate(d.getUTCDate() + 1)
    return d.toISOString().slice(0, h.by === 'month' ? 7 : 10)
  }
  for (let p = h.periods[0].period; p <= h.periods[h.periods.length - 1].period; p = step(p)) out.push({ period: p, watches: have.get(p) ?? 0 })
  return out
}

export function HistoryScreen() {
  const [params, setParams] = useSearchParams()
  const range = rangeOf(params.get('range'))
  const filter: HistoryFilter = { start: range.start?.slice(0, 13), end: range.end, source: params.get('source') ?? undefined }   // the hour, so the query key holds still between renders
  const load = useLoad({ queryKey: keys.history(filter), queryFn: () => api.history(filter) })
  const set = (name: string, value: string) => setParams(p => { const out = new URLSearchParams(p); if (value) out.set(name, value); else out.delete(name); return out }, { replace: true })

  return (
    <>
      <PageHeader title="History" scope="What was watched, from the watch history" finding={load.status === 'ready' ? { text: describeHistory(load.data, range.words) } : undefined} />
      <DataView state={load} isEmpty={h => h.sources.length === 0} skeleton={<HistorySkeleton />} empty={<EmptyState title="No watch history yet">Import a Google Takeout watch history on the Suggestions page, or set history_url and history_table on the server and run tubes history sync.</EmptyState>}>
        {h => (
          <div className="grid gap-8">
            <div className="flex flex-wrap items-end gap-4">
              <Field label="Timeframe" className="min-w-48">
                <NativeSelect value={params.get('range') ?? '12m'} onChange={e => set('range', e.target.value === '12m' ? '' : e.target.value)}>
                  {rangeChoices(h.sources).map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                </NativeSelect>
              </Field>
              {h.sources.length > 1 && (
                <Field label="Account" className="min-w-40">
                  <NativeSelect value={filter.source ?? ''} onChange={e => set('source', e.target.value)}>
                    <option value="">Every account</option>
                    {h.sources.map(s => <option key={s.source} value={s.source}>{s.source}</option>)}
                  </NativeSelect>
                </Field>
              )}
            </div>
            {h.watches > 0 ? <Watched h={h} /> : <EmptyState title="Nothing watched then">Choose a longer timeframe, or All time.</EmptyState>}
          </div>
        )}
      </DataView>
    </>
  )
}

function Watched({ h }: { h: HistoryStats }) {
  const periods = fillPeriods(h)
  const ticks = periods.map((_, i) => i)
  const channels: Column<TopChannel>[] = [
    { key: 'title', header: 'Channel', truncate: true, cell: c => (
      <span className="flex min-w-0 items-center gap-2">
        {c.followed ? <Link to={`/channels/${encodeURIComponent(c.channel_id)}`} className="truncate hover:underline">{channelName(c)}</Link>
          : <a href={withBase(`https://www.youtube.com/channel/${encodeURIComponent(c.channel_id)}`)} target="_blank" rel="noreferrer" className="truncate hover:underline">{channelName(c)}</a>}
        {c.followed && <Status tone="success">Followed</Status>}
      </span>
    ) },
    { key: 'watches', header: 'Watches', numeric: true, cell: c => format.integer(c.watches) },
    { key: 'videos', header: 'Videos', numeric: true, cell: c => format.integer(c.videos) },
    { key: 'last', header: 'Last watched', cell: c => format.date(c.last), className: 'whitespace-nowrap' },
  ]
  const videos: Column<TopVideo>[] = [
    { key: 'title', header: 'Video', truncate: true, cell: v => (
      <span className="flex min-w-0 flex-col">
        <a href={withBase(`https://www.youtube.com/watch?v=${encodeURIComponent(v.video_id)}`)} target="_blank" rel="noreferrer" className="truncate hover:underline">{v.title ?? 'A video no longer on YouTube'}</a>
        {v.channel && <span className="truncate type-caption text-muted-foreground">{v.channel}</span>}
      </span>
    ) },
    { key: 'watches', header: 'Watches', numeric: true, cell: v => format.integer(v.watches) },
    { key: 'last', header: 'Last watched', cell: v => format.date(v.last), className: 'whitespace-nowrap' },
  ]
  return (
    <>
      <section aria-labelledby="over-time" className="grid gap-3">
        <h2 id="over-time" className="type-heading">Watches per {h.by}</h2>
        <LineChart
          label={`Watches per ${h.by}`}
          series={periods.map((p, i) => ({ x: i, y: p.watches }))}
          seriesLabel="Watches"
          formatX={x => periodLabel(periods[Math.round(x)].period, h.by)}
          formatY={y => format.integer(y)}
          xTicks={ticks}
          height={220}
        />
      </section>
      <div className="grid gap-8 lg:grid-cols-2">
        <section aria-labelledby="top-channels" className="grid content-start gap-3">
          <h2 id="top-channels" className="type-heading">Channels watched most</h2>
          <DataTable caption="Channels watched most in this timeframe" columns={channels} rows={h.channels_top} rowKey={c => c.channel_id} />
        </section>
        <section aria-labelledby="top-videos" className="grid content-start gap-3">
          <h2 id="top-videos" className="type-heading">Videos watched most</h2>
          <DataTable caption="Videos watched most in this timeframe" columns={videos} rows={h.videos_top} rowKey={v => v.video_id} />
        </section>
      </div>
    </>
  )
}

/** Mirrors the page: the two selects, the chart, then two tables. */
function HistorySkeleton() {
  return (
    <div className="grid gap-8" aria-hidden>
      <div className="flex gap-4"><Skeleton className="h-10 w-48" /><Skeleton className="h-10 w-40" /></div>
      <Skeleton className="h-56 w-full" />
      <div className="grid gap-8 lg:grid-cols-2"><TableSkeleton rows={8} columns={4} /><TableSkeleton rows={8} columns={3} /></div>
    </div>
  )
}
