// The one question: "What was played here, where was it started from, and how much of each was watched?"
// The finding answers it for the last 30 days in a sentence (plays of how many videos, how many to the end,
// time watched, where most were started). Then, in the order a person asks next: the month in numbers (how the
// plays ended), where plays were started from (a CompositionBar, so the sources compare as parts of one whole),
// then every play, newest first, each opening in place to all that was kept of it (src/tubes/viewing.py: when,
// where from and which one, its place in that list, the running time, the seconds seen, where it stopped), and
// last the visits to channel pages.
//
// This is what the watching side records itself, play by play; the imported Google Takeout history (History)
// stays a separate page, as it has no progress in it. The filters and the open plays live in the URL
// (?outcome=partial&source=home&open=12), so a view can be linked. The list is cursor paged, newest first.
import { Link, useSearchParams } from 'react-router'
import { CompositionBar, DataView, Disclosure, EmptyState, Field, InfiniteList, Metric, MetricStrip, NativeSelect, PageHeader, Skeleton, Status, format, useExpanded, useInfiniteLoad, useLoad, type Tone } from 'strata-react'
import { api, cursorOfRow, describeError, keys, runningTime, type ChannelVisit, type Outcome, type Play, type PlayFilter, type PlaySource, type PlaySummary } from '../api'

/** Each outcome in words, with its tone: the end is the good news, a short look the one to notice. */
export const outcomes: Record<Outcome, { word: string; tone: Tone }> = {
  full: { word: 'Watched to the end', tone: 'success' },
  partial: { word: 'Part watched', tone: 'info' },
  short: { word: 'Short look', tone: 'warning' },
  none: { word: 'Not started', tone: 'neutral' },
}

/** Where a play or a visit was started from, in the watching side's own words. */
export const sources: Record<PlaySource, string> = {
  home: 'Home',
  continue: 'Continue watching',
  channel: 'A channel’s page',
  search: 'Search',
  up_next: 'Up next',
  watch: 'A video’s page',
  rail: 'The side rail',
  chips: 'Home’s channel chips',
  channels: 'Channels',
  link: 'A link or the address bar',
  other: 'Somewhere else',
}

/** A value not known: an en dash. */
const MISSING = '–'

const sourceWord = (s: string) => sources[s as PlaySource] ?? sources.other

/** The sources a play can start from, for the filter (channel visits have their own). */
const playSources: PlaySource[] = ['home', 'continue', 'channel', 'search', 'up_next', 'link']

/** Seconds as hours and minutes: "8 h 44 min", "12 min", "40 s". */
export function timeSpent(seconds: number): string {
  const s = Math.round(seconds)
  if (s < 60) return format.withUnit(s, 's')
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h ? `${format.withUnit(h, 'h')} ${format.withUnit(m, 'min')}` : format.withUnit(m, 'min')
}

/** The share of a video seen, or null when its running time or the seconds seen are not known. */
export function shareSeen(p: Pick<Play, 'watched' | 'length'>): number | null {
  return p.watched !== null && p.length ? Math.min(1, p.watched / p.length) : null
}

/** The page's finding. */
export function describeViewing(s: PlaySummary): string {
  if (!s.plays) return `Nothing has been played here in the last ${format.count(s.days, 'day')}. Each play is kept from the first one.`
  const top = Object.entries(s.sources).sort((a, b) => b[1].plays - a[1].plays)[0]
  return `${format.count(s.plays, 'play')} of ${format.count(s.videos, 'video')} in the last ${format.count(s.days, 'day')}, ${format.integer(s.outcomes.full)} watched to the end, ${timeSpent(s.seconds)} in all. Most started from ${sourceWord(top[0])} (${format.integer(top[1].plays)}).`
}

/** Where plays were started, most first, as at most five parts (the bar has five colours): past four, the rest together as Elsewhere. */
export function sourceParts(s: Pick<PlaySummary, 'sources'>): { key: string; label: string; value: number }[] {
  const all = Object.entries(s.sources).sort((a, b) => b[1].plays - a[1].plays).map(([key, v]) => ({ key, label: sourceWord(key), value: v.plays }))
  if (all.length <= 5) return all
  return [...all.slice(0, 4), { key: 'elsewhere', label: 'Elsewhere', value: all.slice(4).reduce((n, p) => n + p.value, 0) }]
}

/** What `detail` names, in words: the channel, the search words, the video Up next was beside. */
export function describeDetail(r: Pick<Play, 'source' | 'detail' | 'detail_title'>): string | null {
  if (!r.detail) return null
  if (r.source === 'search') return `“${r.detail}”`
  return r.detail_title ?? r.detail
}

export function ViewingScreen() {
  const [params, setParams] = useSearchParams()
  const filter: PlayFilter = { outcome: (params.get('outcome') as Outcome | null) ?? undefined, source: (params.get('source') as PlaySource | null) ?? undefined }
  const summary = useLoad({ queryKey: keys.playSummary, queryFn: api.playSummary })
  const set = (name: string, value: string) => setParams(p => { const out = new URLSearchParams(p); if (value) out.set(name, value); else out.delete(name); out.delete('open'); return out }, { replace: true })

  return (
    <>
      <PageHeader title="Viewing" scope="Every play here, where it was started from and how much was watched" finding={summary.status === 'ready' ? { text: describeViewing(summary.data) } : undefined} />
      <DataView state={summary} isEmpty={s => s.plays === 0} skeleton={<SummarySkeleton />} empty={null}>
        {s => <Month s={s} />}
      </DataView>
      <section aria-labelledby="plays" className="grid gap-4">
        <h2 id="plays" className="type-heading">Plays, newest first</h2>
        <div className="flex flex-wrap items-end gap-4">
          <Field label="How it ended" className="min-w-48">
            <NativeSelect value={filter.outcome ?? ''} onChange={e => set('outcome', e.target.value)}>
              <option value="">Any way</option>
              {(Object.keys(outcomes) as Outcome[]).map(o => <option key={o} value={o}>{outcomes[o].word}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Started from" className="min-w-48">
            <NativeSelect value={filter.source ?? ''} onChange={e => set('source', e.target.value)}>
              <option value="">Anywhere</option>
              {playSources.map(s => <option key={s} value={s}>{sources[s]}</option>)}
            </NativeSelect>
          </Field>
        </div>
        <Plays filter={filter} />
      </section>
      <section aria-labelledby="visits" className="grid gap-4">
        <h2 id="visits" className="type-heading">Channel pages visited</h2>
        <Visits />
      </section>
    </>
  )
}

/** The last 30 days in numbers, and where the plays were started. */
function Month({ s }: { s: PlaySummary }) {
  const parts = sourceParts(s)
  return (
    <div className="grid gap-8">
      <MetricStrip label={`The last ${format.count(s.days, 'day')}`}>
        <Metric label="Plays" value={format.integer(s.plays)} note={format.count(s.videos, 'different video')} />
        <Metric label="To the end" value={format.integer(s.outcomes.full)} note={`${format.percent(s.outcomes.full / s.plays)} of plays · 90% and more seen`} />
        <Metric label="Part watched" value={format.integer(s.outcomes.partial)} note="A tenth or more, under 90%" />
        <Metric label="Short looks" value={format.integer(s.outcomes.short + s.outcomes.none)} note="Under a tenth, or never started" />
        <Metric label="Time watched" value={timeSpent(s.seconds)} note="Each second counted once" />
      </MetricStrip>
      <CompositionBar label="Where plays were started" parts={parts} formatValue={v => format.count(v, 'play')} partHeader="Started from" valueHeader="Plays" />
    </div>
  )
}

function Plays({ filter }: { filter: PlayFilter }) {
  const load = useInfiniteLoad({
    queryKey: keys.plays(filter),
    queryFn: ({ cursor, signal }) => api.plays(filter, cursor, signal),
    items: page => page.items,
    itemKey: p => String(p.id),
    hasMore: page => page.has_more,
    cursorAfter: cursorOfRow,
    describeError,
  })
  const open = useExpanded({ param: 'open' })
  const filtered = Boolean(filter.outcome || filter.source)
  return (
    <InfiniteList
      state={load}
      label="Plays, newest first"
      skeleton={<RowsSkeleton rows={8} />}
      moreSkeleton={<RowsSkeleton rows={2} />}
      moreLabel="Show older plays"
      end={<p className="type-caption text-muted-foreground">That is every play kept.</p>}
      empty={filtered
        ? <EmptyState title="No plays like that">Choose Any way or Anywhere to see more.</EmptyState>
        : <EmptyState title="Nothing played yet">Each video played on the watching side is listed here, with where it was started from and how much of it was seen.</EmptyState>}
    >
      {p => <PlayRow p={p} open={open.isOpen(String(p.id))} onOpenChange={o => open.setOpen(String(p.id), o)} />}
    </InfiniteList>
  )
}

function PlayRow({ p, open, onOpenChange }: { p: Play; open: boolean; onOpenChange: (open: boolean) => void }) {
  const share = shareSeen(p)
  const summary = (
    <span className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-1">
      <span className="grid min-w-0 flex-1">
        <span className="truncate type-body">{p.title ?? p.video_id}</span>
        <span className="truncate type-caption text-muted-foreground">{format.dateTime(p.at)} · {sourceWord(p.source)}{p.channel ? ` · ${p.channel}` : ''}</span>
      </span>
      <span className="flex items-center gap-3">
        <span className="tabular-nums type-body-sm text-muted-foreground">{share === null ? MISSING : format.percent(share)}</span>
        <Status tone={outcomes[p.outcome].tone}>{outcomes[p.outcome].word}</Status>
      </span>
    </span>
  )
  return (
    <Disclosure summary={summary} open={open} onOpenChange={onOpenChange} className="border-b border-border">
      <dl className="grid max-w-2xl gap-2 pb-4 type-body-sm">
        <Detail term="Video"><Link to={`/watch/${encodeURIComponent(p.video_id)}`} className="hover:underline">{p.title ?? p.video_id}</Link></Detail>
        <Detail term="Channel">{p.channel_id ? <Link to={`/channels/${encodeURIComponent(p.channel_id)}`} className="hover:underline">{p.channel ?? p.channel_id}</Link> : MISSING}</Detail>
        <Detail term="Started">{format.dateTime(p.at)}</Detail>
        <Detail term="Last report">{p.updated ? format.dateTime(p.updated) : 'None: the picture never started'}</Detail>
        <Detail term="Started from">{sourceWord(p.source)}{describeDetail(p) ? `: ${describeDetail(p)}` : ''}</Detail>
        <Detail term="Place in that list">{p.rank === null ? MISSING : format.integer(p.rank + 1)}</Detail>
        <Detail term="Running time">{runningTime(p.length)}</Detail>
        <Detail term="Seen">{p.watched === null ? 'Not kept for this play' : `${runningTime(p.watched)}${share === null ? '' : ` (${format.percent(share)})`}`}</Detail>
        <Detail term="Stopped at">{runningTime(p.position)}</Detail>
        <Detail term="Play">{`#${p.id}`}</Detail>
      </dl>
    </Disclosure>
  )
}

function Detail({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-6">
      <dt className="w-36 shrink-0 text-muted-foreground">{term}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

function Visits() {
  const load = useInfiniteLoad({
    queryKey: keys.channelVisits,
    queryFn: ({ cursor, signal }) => api.channelVisits(cursor, signal),
    items: page => page.items,
    itemKey: v => String(v.id),
    hasMore: page => page.has_more,
    cursorAfter: cursorOfRow,
    describeError,
  })
  return (
    <InfiniteList
      state={load}
      label="Channel pages visited, newest first"
      skeleton={<RowsSkeleton rows={4} />}
      moreSkeleton={<RowsSkeleton rows={2} />}
      moreLabel="Show older visits"
      end={<p className="type-caption text-muted-foreground">That is every visit kept.</p>}
      empty={<EmptyState title="No channel pages visited yet">Each visit to a channel’s page is listed here, with where it was opened from.</EmptyState>}
    >
      {v => <VisitRow v={v} />}
    </InfiniteList>
  )
}

function VisitRow({ v }: { v: ChannelVisit }) {
  const from = v.detail_title ?? v.detail
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border py-3">
      <Link to={`/channels/${encodeURIComponent(v.channel_id)}`} className="min-w-0 truncate type-body hover:underline">{v.title ?? v.channel_id}</Link>
      <span className="truncate type-caption text-muted-foreground">{format.dateTime(v.at)} · from {sourceWord(v.source)}{from ? `: ${from}` : ''}</span>
    </div>
  )
}

/** Mirrors the numbers and the bar. */
function SummarySkeleton() {
  return (
    <div className="grid gap-8" aria-hidden>
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  )
}

/** Mirrors a list's rows: a title and a line under it, the share and the outcome at the end. */
function RowsSkeleton({ rows }: { rows: number }) {
  return (
    <div className="grid" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-border py-3">
          <div className="grid flex-1 gap-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-1/3" /></div>
          <Skeleton className="h-5 w-24" />
        </div>
      ))}
    </div>
  )
}
