// The one question: "Which channels does the library follow, and is each one up to date?" The
// finding answers it in a sentence (how many channels and videos, how many are still being read
// back to their first upload, when the last full sync ran), or says what stops it working (no
// YouTube key). Then, in the order a person asks next: is a sync running and how far has it got,
// add a channel or a video (one field takes a link, an id or an @handle), and the channels.
//
// This is the storage service's YouTube page, ported: add a channel, Sync its videos, sync the
// chosen channels in bulk, Resync (here "Start again") and Delete. The server runs a sync in the
// background, one at a time, so the page starts it and polls its progress instead of looping over
// requests itself as storage's page did. A new channel's sync starts as soon as it is added.
//
// Patterns: useLoad -> DataView for the channels; useSelection -> DataTable selection -> BulkBar
// for Sync N channels, which holds the view's one filled button while channels are chosen (Sync all
// steps down to outline); RowAction per row, shown only where it applies; removal through
// useUndoable (Undo for a few seconds, then the request), since it can be undone by adding the
// channel again but takes its videos with it; sort in the URL.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { AsyncButton, BulkBar, Button, DataTable, DataView, EmptyState, Field, Input, PageHeader, RowAction, Status, TableSkeleton, UndoBar, format, useAsyncAction, useLoad, useSelection, useUndoable, type Column } from 'strata-react'
import { api, describeError, keys, type Added, type Channel, type LibraryStatus, type SyncJob } from '../api'

/** The page's finding. */
export function describeLibrary(channels: Channel[], status: LibraryStatus): string {
  if (!status.configured) return 'Nothing can be added or synced until the server has a YouTube key: put YOUTUBE_API_KEY in its environment and restart it.'
  const followed = channels.filter(c => c.follow !== false)
  if (!followed.length) return 'The library follows no channels yet. Add one below by its link or @handle; its videos are fetched at once.'
  const behind = followed.filter(c => !c.complete).length
  const videos = channels.reduce((n, c) => n + c.videos, 0)
  const head = `${format.count(videos, 'video')} from ${format.count(followed.length, 'followed channel')}.`
  const back = behind ? ` ${format.count(behind, 'channel is', 'channels are')} still being read back to the first upload.` : ''
  const when = status.synced ? ` Every channel was last synced on ${format.dateTime(status.synced)}.` : ' Not every channel has been synced yet.'
  const hidden = status.hidden ? ` ${format.count(status.hidden, 'video is', 'videos are')} hidden because YouTube no longer has them.` : ''
  const live = status.live ? ` ${format.count(status.live, 'live or scheduled stream is', 'live or scheduled streams are')} hidden until ${status.live === 1 ? 'it ends' : 'they end'}.` : ''
  return head + back + when + hidden + live
}

/** How far the sync has got, or how the last one went. Undefined before any sync since the server started. */
export function describeJob(job: SyncJob): string | undefined {
  const added = format.count(job.added, 'new video')
  if (job.running) return job.current ? `Syncing ${format.integer(Math.min(job.done + 1, job.total))} of ${format.integer(job.total)}: ${job.current}. ${added} so far.` : `Starting a sync of ${format.count(job.total, 'channel')}.`
  if (!job.finished) return undefined
  const channels = job.errors.filter(e => e.channel).length
  const stopped = job.errors.some(e => !e.channel && !e.title)     // an error naming nothing stopped the whole sync
  const failed = channels ? ` ${format.count(channels, 'channel')} failed.` : stopped ? ' It stopped part way.' : ''
  const gone = job.gone ? ` ${format.count(job.gone, 'video')} gone from YouTube ${job.gone === 1 ? 'is' : 'are'} now hidden.` : ''
  return `The last sync, of ${format.count(job.total, 'channel')}, added ${added}.${gone}${failed}`
}

/** A channel's state, in a word. */
export function channelState(c: Channel): { tone: 'success' | 'info' | 'warning' | 'neutral'; word: string } {
  if (c.follow === false) return { tone: 'neutral', word: 'Not followed' }
  if (c.complete) return { tone: 'success', word: 'Up to date' }
  if (c.synced || c.resumable) return { tone: 'info', word: 'Reading back' }
  return { tone: 'warning', word: 'Not synced' }
}

/** What was added, in a sentence. */
export function describeAdded(a: Added): string {
  return a.kind === 'channel' ? `Following ${a.channel.title}. Its videos are being fetched.` : `Added “${a.video.title}”${a.video.channel ? ` from ${a.video.channel}` : ''}.`
}

const key = (c: Channel) => c.id
const totalOf = (c: Channel) => c.total_videos ?? -1
const syncedAt = (c: Channel) => c.synced ?? ''     // never synced sorts first

export function LibraryScreen() {
  const queryClient = useQueryClient()
  const load = useLoad({ queryKey: keys.channels, queryFn: api.channels })
  const status = useLoad({ queryKey: keys.library, queryFn: api.library })
  const job = useLoad({ queryKey: keys.sync, queryFn: api.syncJob, refetchInterval: q => (q.state.data?.running ? 2000 : false) })
  const running = job.status === 'ready' && job.data.running
  const undoable = useUndoable()

  // When a sync finishes, what it changed is read again.
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !running) for (const queryKey of [keys.channels, keys.library, keys.videos, keys.system]) void queryClient.invalidateQueries({ queryKey })
    wasRunning.current = running
  }, [running, queryClient])

  const started = async (j: SyncJob) => { queryClient.setQueryData(keys.sync, j); await queryClient.invalidateQueries({ queryKey: keys.channels }) }
  const syncAll = useAsyncAction(async () => started(await api.sync()), { describeError })
  const syncSome = useAsyncAction(async (ids: string[]) => { await started(await api.sync(ids)); selection.clear() }, { describeError })
  const restart = useAsyncAction(async (c: Channel) => started((await api.restartChannel(c.id)).sync), { describeError })
  const follow = useAsyncAction(async (c: Channel) => started(((await api.add(c.id)) as Extract<Added, { kind: 'channel' }>).sync), { describeError })   // a channel's id adds the channel

  const rows = load.status === 'ready' ? load.data.filter(c => !undoable.isRemoved(key(c))) : []
  const selection = useSelection(rows, key)
  const configured = status.status === 'ready' && status.data.configured

  const remove = (c: Channel) => undoable.schedule({
    id: c.id,
    message: `Removed ${c.title} and its ${format.count(c.videos, 'video')}.`,
    failure: `${c.title} is back: removing it did not go through.`,
    commit: async () => {
      try { await api.removeChannel(c.id) } finally { for (const queryKey of [keys.channels, keys.library, keys.videos]) await queryClient.invalidateQueries({ queryKey }) }
    },
  })

  const columns: Column<Channel>[] = [
    {
      key: 'title', header: 'Channel', truncate: true, sort: (a, b) => a.title.localeCompare(b.title),
      cell: c => (
        <span className="flex min-w-0 flex-col">
          <Link to={`/channels/${encodeURIComponent(c.id)}`} className="truncate hover:underline">{c.title}</Link>
          {c.handle && <span className="truncate type-caption text-muted-foreground">{c.handle}</span>}
        </span>
      ),
    },
    { key: 'videos', header: 'Here', numeric: true, cell: c => (
      <span className="grid">
        {format.integer(c.videos)}
        {!!c.hidden && <span className="type-caption text-muted-foreground">{format.integer(c.hidden)} hidden</span>}
      </span>
    ), sort: (a, b) => a.videos - b.videos },
    { key: 'total', header: 'On YouTube', numeric: true, cell: c => (c.total_videos == null ? '–' : format.integer(c.total_videos)), sort: (a, b) => totalOf(a) - totalOf(b) },
    { key: 'state', header: 'State', cell: c => { const s = channelState(c); return <Status tone={s.tone}>{s.word}</Status> } },
    { key: 'synced', header: 'Last synced', cell: c => (c.synced ? format.dateTime(c.synced) : 'Never'), sort: (a, b) => syncedAt(a).localeCompare(syncedAt(b)), className: 'whitespace-nowrap' },
    {
      key: 'actions', header: 'Actions', hideHeader: true, cell: c => (
        <span className="flex justify-end gap-1">
          {configured && c.follow !== false && <RowAction label="Sync" subject={c.title} disabled={running} onClick={() => void syncSome.run([c.id])} />}
          {configured && c.follow !== false && <RowAction label="Start again" subject={c.title} disabled={running} onClick={() => void restart.run(c)} />}
          {configured && c.follow === false && <RowAction label="Follow" subject={c.title} onClick={() => void follow.run(c)} />}
          <RowAction label="Remove" subject={c.title} onClick={() => remove(c)} />
        </span>
      ),
    },
  ]

  const failure = [syncSome, restart, follow].find(a => a.phase === 'error')

  return (
    <>
      <PageHeader
        title="Library"
        scope="Channels and videos from YouTube"
        finding={load.status === 'ready' && status.status === 'ready' ? { text: describeLibrary(load.data, status.data) } : undefined}
        actions={configured ? (
          <AsyncButton variant={selection.count ? 'outline' : 'default'} disabled={running} phase={syncAll.phase} error={syncAll.error} labels={{ idle: 'Sync all', pending: 'Starting…', done: 'Started' }} onClick={() => void syncAll.run()} />
        ) : undefined}
      />

      {job.status === 'ready' && <SyncProgress job={job.data} />}
      {failure && <p role="alert" className="type-body-sm text-danger">{failure.error}</p>}

      {configured && <AddForm onAdded={started} />}

      <section aria-labelledby="channels" className="grid gap-3">
        <h2 id="channels" className="type-heading">Channels</h2>
        <DataView
          state={load}
          isEmpty={() => rows.length === 0}
          skeleton={<TableSkeleton rows={6} columns={6} />}
          empty={<EmptyState title="No channels yet">Add a channel above by pasting its link or typing its @handle. Every video it has posted is fetched, and new ones arrive with each sync.</EmptyState>}
        >
          {() => (
            <div className="grid gap-3">
              <BulkBar count={selection.count} noun="channel" onClear={selection.clear}>
                <Button size="sm" variant="default" disabled={running} onClick={() => void syncSome.run(selection.selectedRows.map(key))}>
                  Sync {format.integer(selection.count)}
                </Button>
              </BulkBar>
              <DataTable
                caption="Channels in the library, by title"
                columns={columns}
                rows={rows}
                rowKey={key}
                sortParam="sort"
                selection={configured ? { ...selection, rowLabel: c => c.title, isSelectable: c => c.follow !== false } : undefined}
              />
            </div>
          )}
        </DataView>
      </section>
      <UndoBar undoable={undoable} />
    </>
  )
}

/** The running sync, or how the last one went, with any channel that failed and why. */
export function SyncProgress({ job }: { job: SyncJob }) {
  const text = describeJob(job)
  if (!text) return null
  return (
    <section aria-label="Sync" className="grid max-w-3xl gap-2">
      <p role="status" className="flex flex-wrap items-center gap-3 type-body-sm">
        {job.running ? <Status tone="info">Syncing</Status> : job.errors.length ? <Status tone="warning">Finished with failures</Status> : <Status tone="success">Finished</Status>}
        <span className="tabular-nums">{text}</span>
      </p>
      {!job.running && job.errors.length > 0 && (
        <ul className="grid gap-1 type-body-sm text-muted-foreground">
          {job.errors.map((e, i) => <li key={e.channel ?? i}><span className="text-foreground">{e.title ?? 'The sync'}</span>: {e.error}</li>)}
        </ul>
      )}
    </section>
  )
}

/** Add a channel or a video. Its own component so typing does not re-render the table. */
export function AddForm({ onAdded }: { onAdded: (j: SyncJob) => Promise<void> }) {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const [problem, setProblem] = useState<string>()
  const [added, setAdded] = useState<Added>()
  const add = useAsyncAction(async () => {
    const a = await api.add(text.trim())
    setAdded(a); setText('')
    if (a.kind === 'channel') await onAdded(a.sync)
    else for (const queryKey of [keys.channels, keys.videos, keys.library]) await queryClient.invalidateQueries({ queryKey })
  }, { describeError })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const p = text.trim() ? undefined : 'Paste a channel or video link, or type an id or @handle.'
    setProblem(p)
    if (!p) void add.run()
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-labelledby="add" className="grid max-w-xl gap-3">
      <h2 id="add" className="type-heading">Add to the library</h2>
      <Field label="Channel or video" hint="A channel is followed: every video it has posted is fetched, and new ones with each sync. A video's link adds just that video." error={problem ?? (add.phase === 'error' ? add.error : undefined)}>
        <Input value={text} onChange={e => setText(e.target.value)} placeholder="https://www.youtube.com/@channel" autoComplete="off" spellCheck={false} />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" phase={add.phase} error={add.error} labels={{ idle: 'Add', pending: 'Adding…', done: 'Added' }} />
        {added && add.phase !== 'error' && <p role="status" className="type-body-sm">{describeAdded(added)}</p>}
      </div>
    </form>
  )
}
