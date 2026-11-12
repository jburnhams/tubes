// The one question: "How much of today's YouTube quota is left, and what used it?" Google gives a key
// 10,000 units a day by default, resets them at midnight Pacific and has no call that says how many
// are left, so the server counts every call it makes (quota.py) and this page reads that count. The
// finding says what is used and left and when it resets, or that YouTube has refused a call (then
// nothing is left, whoever spent it), or that there is no key. Then, in the order a person asks
// next: the level against the limit (a Meter whose thresholds warn before a sync would be cut off),
// what today's units went on (a CompositionBar of purposes: syncing, rechecking, adding...), which
// endpoints they were spent on, and the last 30 days (a line of units per day and a table of the days
// that used any). The read is polled like the System page's; a poll that fails keeps the last
// counts and says how old they are.
import { CompositionBar, DataTable, DataView, EmptyState, LineChart, Meter, Metric, MetricStrip, PageHeader, Skeleton, StaleNotice, TableSkeleton, crossedThreshold, format, useLoad, type Column, type MeterThreshold } from 'strata-react'
import { api, keys, type QuotaPurpose, type QuotaUsage } from '../api'

/** Warn while a full sync could still fit, and again when it could not. */
export const quotaThresholds: MeterThreshold[] = [
  { at: 0.8, tone: 'warning', label: 'Running low' },
  { at: 0.95, tone: 'danger', label: 'Nearly spent' },
]

const purposes: Record<string, string> = {
  sync: 'Syncing channels',
  recheck: 'Rechecking videos',
  add: 'Adding channels and videos',
  reported: 'Checking videos found missing',
  past: 'Rechecking past streams',
  suggestions: 'Looking up suggestions',
  history: 'Importing history',
  related: 'Finding related channels',
  other: 'Other',
}

/** What a purpose is called on the page; one the page does not know yet is shown by its name. */
export const purposeLabel = (p: QuotaPurpose) => purposes[p] ?? p

/** A figure in quota units. */
export const units = (n: number) => format.withUnit(n, n === 1 ? 'unit' : 'units', format.integer)

/** The reset time in the viewer's own clock, with what it is in Google's. */
const reset = (q: QuotaUsage) => `${format.clock(q.resets)} (midnight Pacific)`

/** The page's finding. */
export function describeQuota(q: QuotaUsage): string {
  if (!q.configured && !q.used) return 'The server has no YouTube key, so no quota is being used. Put YOUTUBE_API_KEY in its environment and restart it.'
  if (q.refused) return `YouTube refused a call at ${format.clock(q.refused)} because the key’s quota is spent, so nothing more can be added, synced or rechecked until it resets at ${reset(q)}.`
  if (!q.used) return `Nothing has been asked of YouTube today. All ${units(q.limit)} are there until the reset at ${reset(q)}.`
  const top = q.today.purposes[0]
  const crossed = crossedThreshold(q.used / q.limit, quotaThresholds)
  const warn = crossed ? ` ${crossed.label}: a sync may stop part way and carry on after the reset.` : ''
  return `${units(q.used)} of ${format.integer(q.limit)} used today, ${units(q.remaining)} left until the reset at ${reset(q)}. Most went on ${purposeLabel(top.purpose).toLowerCase()}.${warn}`
}

/** A day (YYYY-MM-DD, Pacific) as a short label: `9 Nov`. */
export const dayLabel = (day: string) => new Date(`${day}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })

/** The purpose a day's units mostly went on, or null on a day with none. */
export function mostlyOn(d: QuotaUsage['days'][number]): string | null {
  const top = Object.entries(d.purposes).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]
  return top ? purposeLabel(top[0]) : null
}

type Day = QuotaUsage['days'][number]
type Endpoint = QuotaUsage['today']['endpoints'][number]

const failed = (n: number) => (n ? format.integer(n) : '–')

const dayColumns: Column<Day>[] = [
  { key: 'day', header: 'Day (Pacific)', cell: d => format.date(`${d.day}T12:00:00Z`), className: 'whitespace-nowrap' },
  { key: 'units', header: 'Units', numeric: true, cell: d => format.integer(d.units) },
  { key: 'calls', header: 'Calls', numeric: true, cell: d => format.integer(d.calls) },
  { key: 'failed', header: 'Failed', numeric: true, cell: d => failed(d.failed) },
  { key: 'refused', header: 'Ran out', cell: d => (d.refused ? 'Yes' : '–') },
  { key: 'mostly', header: 'Mostly on', cell: d => mostlyOn(d) },                  // a day in this table used quota, so it went on something
]

const endpointColumns: Column<Endpoint>[] = [
  { key: 'endpoint', header: 'Endpoint', cell: e => e.endpoint },
  { key: 'calls', header: 'Calls', numeric: true, cell: e => format.integer(e.calls) },
  { key: 'units', header: 'Units', numeric: true, cell: e => format.integer(e.units) },
  { key: 'failed', header: 'Failed', numeric: true, cell: e => failed(e.failed) },
]

function QuotaSkeleton() {
  return (
    <div className="grid gap-10" aria-hidden>
      <Skeleton className="h-16 w-full max-w-xl" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-32 w-full max-w-3xl" />
      <TableSkeleton rows={3} columns={4} />
    </div>
  )
}

export function QuotaScreen() {
  const load = useLoad({ queryKey: keys.quota, queryFn: api.quota, refetchInterval: 60_000 })
  return (
    <>
      <PageHeader title="YouTube quota" scope="The YouTube key’s daily allowance, as this server has counted its calls" finding={load.status === 'ready' ? { text: describeQuota(load.data) } : undefined} />
      <DataView
        state={load}
        isEmpty={() => false}
        skeleton={<QuotaSkeleton />}
        staleNotice={stale => <StaleNotice stale={stale} shown={when => `These counts are from ${when}.`} />}
        empty={<EmptyState title="No counts">The server sent nothing to report.</EmptyState>}
      >
        {q => <Quota q={q} />}
      </DataView>
    </>
  )
}

function Quota({ q }: { q: QuotaUsage }) {
  const days = [...q.days].reverse()
  const counted = q.days.filter(d => d.calls)
  return (
    <div className="grid gap-10">
      <section aria-labelledby="today" className="grid gap-4">
        <h2 id="today" className="type-heading">Today</h2>
        <Meter
          className="max-w-xl"
          label="Quota used today"
          value={q.refused ? q.limit : Math.min(q.used, q.limit)}
          max={q.limit}
          valueText={q.refused ? 'Spent' : undefined}
          thresholds={quotaThresholds}
          detail={`${format.integer(q.used)} of ${units(q.limit)}`}
        />
        <MetricStrip label="Today’s quota">
          <Metric label="Used" value={format.integer(q.used)} unit="units" note={`${format.count(q.today.calls, 'call')} to YouTube`} />
          <Metric label="Left" value={format.integer(q.remaining)} unit="units" note={q.refused ? 'YouTube has refused a call' : `of ${format.integer(q.limit)} a day`} />
          <Metric label="Failed calls" value={format.integer(q.today.failed)} note="They still cost their units" />
          <Metric label="Resets" value={format.clock(q.resets)} note={`Midnight Pacific, ${format.day(q.resets)}`} />
        </MetricStrip>
      </section>

      <section aria-labelledby="spent-on" className="grid gap-4">
        <h2 id="spent-on" className="type-heading">What it went on</h2>
        {q.today.calls ? (
          <div className="grid gap-8 lg:grid-cols-2">
            <CompositionBar
              label="Today’s units by purpose"
              parts={q.today.purposes.map(p => ({ key: p.purpose, label: purposeLabel(p.purpose), value: p.units }))}
              formatValue={units}
              partHeader="Purpose"
              valueHeader="Units"
              total={q.refused ? q.used : Math.max(q.limit, q.used)}          // refused: nothing is left, whatever this server counted
              restLabel="Left"
            />
            <DataTable caption="Today’s calls by endpoint" columns={endpointColumns} rows={q.today.endpoints} rowKey={e => e.endpoint} />
          </div>
        ) : (
          <EmptyState title="Nothing asked of YouTube yet today">Syncs, rechecks and adding channels each use quota; what they use shows here as they run.</EmptyState>
        )}
      </section>

      <section aria-labelledby="days" className="grid gap-4">
        <h2 id="days" className="type-heading">The last 30 days</h2>
        <LineChart
          label="Quota units used per day, the last 30 days"
          series={days.map((d, i) => ({ x: i, y: d.units }))}
          seriesLabel="Units used"
          formatX={x => dayLabel(days[Math.round(x)].day)}
          formatY={y => format.integer(y)}
          xTicks={days.map((_, i) => i)}
          yMax={q.limit}
          height={220}
        />
        {counted.length ? (
          <DataTable caption="Days that used quota, newest first" columns={dayColumns} rows={counted} rowKey={d => d.day} />
        ) : (
          <EmptyState title="No quota used in 30 days">The server counts each call as it makes it; there have been none.</EmptyState>
        )}
        <p className="max-w-2xl type-body-sm text-muted-foreground">
          Counted by this server as it calls YouTube. Another app using the same key is not counted here, though a refusal it causes is. Google’s Cloud console has the key’s own figures.
        </p>
      </section>
    </div>
  )
}
