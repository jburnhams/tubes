// The one question: "How full is the cache, and what goes first when it fills?" The finding says
// how much is used of the limit and where trimming starts. A Meter draws it against the trimming
// line; then the copies in the order eviction would keep them (highest score first), each with why
// it is kept if it is protected. A copy can be pinned (never evicted) or deleted now; deleting is
// reversible for a few seconds (useUndoable), since the video is fetched again when next played
// anyway, it is not a confirm dialog. Trim now runs eviction at once instead of waiting for the timer.
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { AsyncButton, DataTable, DataView, EmptyState, Meter, Metric, MetricStrip, PageHeader, RowAction, Status, TableSkeleton, UndoBar, format, useAsyncAction, useLoad, useUndoable, type Column, type MeterThreshold } from 'strata-react'
import { api, describeError, keys, type CacheItem, type CacheReport, type Evicted } from '../api'

/** One threshold, the server's own: above 95% of the limit, eviction runs. */
export const cacheThresholds: MeterThreshold[] = [{ at: 0.95, tone: 'warning', label: 'Trimming' }]

/** The page's finding. */
export function describeCache(r: CacheReport): string {
  // Each size in its own unit: in the limit's, a cache of a few gigabytes would read "0 TB of 1 TB".
  if (!r.count) return `The cache is empty. A video is fetched into it the first time it is played; the limit is ${format.bytes(r.limit)}.`
  const over = r.used > r.high
  return `${format.bytes(r.used)} of ${format.bytes(r.limit)} used by ${format.count(r.count, 'video')}. ${over ? 'That is over the trimming line, so the lowest scores go next.' : `Trimming starts at ${format.bytes(r.high)} and stops under ${format.bytes(r.low)}.`}`
}

/** What eviction just did, in a sentence. */
export function describeEvicted(e: Evicted): string {
  return e.evicted.length ? `Freed ${format.bytes(e.freed)} from ${format.count(e.evicted.length, 'video')}.` : 'Nothing needed to go: the cache is under its trimming line.'
}

function StateWord({ i }: { i: CacheItem }) {
  if (i.state === 'ready') return <Status tone="success">Saved</Status>
  if (i.state === 'fetching') return <Status tone="info">Fetching</Status>
  return <Status tone="danger">Failed</Status>
}

const key = (i: CacheItem) => i.video_id

export function CacheScreen() {
  const load = useLoad({ queryKey: keys.cache, queryFn: api.cache })
  const queryClient = useQueryClient()
  const undoable = useUndoable()
  const refresh = () => Promise.all([keys.cache, keys.videos, keys.system].map(queryKey => queryClient.invalidateQueries({ queryKey })))
  const [trimmed, setTrimmed] = useState<Evicted>()
  const trim = useAsyncAction(async () => { setTrimmed(await api.evict()); await refresh() }, { describeError })
  const pin = useAsyncAction(async (i: CacheItem) => { await api.pin(i.video_id, !i.pinned); await refresh() }, { describeError })

  const drop = (i: CacheItem) => undoable.schedule({
    id: i.video_id,
    message: `Deleted the copy of “${i.title}”.`,
    failure: `The copy of “${i.title}” is back: deleting it did not go through.`,
    commit: async () => { try { await api.dropCopy(i.video_id) } finally { await refresh() } },
  })

  const columns: Column<CacheItem>[] = [
    { key: 'title', header: 'Video', truncate: true, cell: i => <Link to={`/watch/${encodeURIComponent(i.video_id)}`} className="hover:underline">{i.title}</Link> },
    { key: 'state', header: 'Copy', cell: i => <StateWord i={i} /> },
    { key: 'bytes', header: 'Size', numeric: true, cell: i => format.bytes(i.bytes), sort: (a, b) => a.bytes - b.bytes },
    { key: 'plays', header: 'Plays', numeric: true, cell: i => format.integer(i.plays), sort: (a, b) => a.plays - b.plays },
    { key: 'last', header: 'Last played', cell: i => (i.last_played ? format.dateTime(i.last_played) : 'Never'), className: 'whitespace-nowrap' },
    { key: 'score', header: 'Score', numeric: true, cell: i => format.decimal(i.score), sort: (a, b) => a.score - b.score },
    { key: 'kept', header: 'Kept because', cell: i => i.protected ?? (i.state === 'failed' ? 'Goes first' : '–') },
    {
      key: 'actions', header: 'Actions', hideHeader: true, cell: i => (
        <span className="flex justify-end gap-1">
          {i.state !== 'failed' && <RowAction label={i.pinned ? 'Unpin' : 'Pin'} subject={i.title} onClick={() => void pin.run(i)} />}
          <RowAction label="Delete" subject={i.title} onClick={() => drop(i)} />
        </span>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Cache"
        scope="Copies on this server's disk, highest score first"
        finding={load.status === 'ready' ? { text: describeCache(load.data) } : undefined}
        actions={<AsyncButton variant="default" phase={trim.phase} error={trim.error} labels={{ idle: 'Trim now', pending: 'Trimming…', done: 'Trimmed' }} onClick={() => void trim.run()} />}
      />
      {trimmed && <p role="status" className="type-body-sm">{describeEvicted(trimmed)}</p>}
      {pin.phase === 'error' && <p role="alert" className="type-body-sm text-danger">{pin.error} The pin was not changed.</p>}
      <DataView
        state={load}
        isEmpty={() => false}
        skeleton={<TableSkeleton rows={6} columns={7} />}
        empty={null}
      >
        {r => {
          const rows = r.items.filter(i => !undoable.isRemoved(key(i)))
          return (
            <div className="grid gap-8">
              <div className="grid max-w-xl gap-3">
                <Meter label="Cache used" value={r.used} max={r.limit} thresholds={cacheThresholds} detail={`${format.bytes(r.used)} of ${format.bytes(r.limit)}`} />
              </div>
              <MetricStrip label="Copies">
                <Metric label="Saved" value={format.integer(r.by_state.ready)} note="Play at once" />
                <Metric label="Being fetched" value={format.integer(r.by_state.fetching)} note="Playing while they arrive" />
                <Metric label="Failed" value={format.integer(r.by_state.failed)} note="Fetched again when played" />
              </MetricStrip>
              {rows.length ? (
                <DataTable caption="Copies, highest score first" columns={columns} rows={rows} rowKey={key} sortParam="sort" />
              ) : (
                <EmptyState title="Nothing in the cache">A video is fetched into the cache the first time it is played, and stays while it scores well.</EmptyState>
              )}
            </div>
          )
        }}
      </DataView>
      <UndoBar undoable={undoable} />
    </>
  )
}
