// The one question: "Which channels should the library take in?", from the watch history and from
// what the followed and most watched channels point at (their watch pages list its videos next, or
// they feature it: related.py on the server, asked again weekly). The finding answers it in a
// sentence (how many channels are left to consider, from which histories, how many related channels
// point at, how many were followed or dismissed so far), or says how to bring a history in. Then, in
// the order a person asks next: narrow the list (a group of channels watched in the same sittings,
// one of YouTube's topics, what a channel says of its audience, or the dismissed ones), order it
// (most watched, or pointed at by the most of your channels: the same channels coming up again and
// again is the clustering), name the group being looked at, and work through the list.
//
// A list pasted into the box at the top (links, @handles or names, YouTube or iPlayer, one a line:
// paste.py on the server) joins the list as suggestions, and the page then shows only what was
// pasted (`pasted=true`, latest first), so a list from elsewhere is followed one key at a time. An
// iPlayer programme needs no YouTube key to follow; its row says iPlayer.
//
// The list is a queue worked from the keyboard (useActiveItem + ActiveList, j/k to move): f follows
// the active channel (all its uploads, synced at once, as Library's Add does), a adds only the videos
// of it that were watched, d dismisses it. Following takes it off the list (it is in the library
// now; Library's Remove undoes it); dismissing goes through useUndoable, so Undo brings it back for
// a few seconds, and the dismissed tab restores one later. Best score first: watches added up,
// each counting half as much a year on, so old favourites and new ones both rank. A channel only
// pointed at has no watches, so "Add watched videos" is not offered for it; each row says which of
// your channels point at it.
//
// A history comes in through the form at the foot (a Takeout watch-history.json or .html under a
// name), or `tubes history import` on the server; the server groups the channels and asks YouTube
// for their topics when it imports, and Refresh does both again.
import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { ActiveList, AsyncButton, DataView, EmptyState, Field, Input, Textarea, KeysLegend, NativeSelect, PageHeader, RowAction, Skeleton, Status, Tabs, Thumbnail, UndoBar, format, useActiveItem, useAsyncAction, useHotkeys, useLoad, useUndoable, type Shortcut } from 'strata-react'
import { api, describeError, keys, withBase, type Pasted, type Suggestion, type SuggestionFilter, type SuggestionGroup, type SuggestionSummary, type SyncJob, type Added } from '../api'

const views = [
  { value: 'open', label: 'To consider' },
  { value: 'dismissed', label: 'Dismissed' },
]

/** Whether there is anything to show: a history, or channels related ones point at (open or dismissed). */
export function hasSuggestions(s: SuggestionSummary): boolean {
  return s.sources.length > 0 || s.open > 0 || s.dismissed > 0
}

/** The page's finding. */
export function describeSuggestions(s: SuggestionSummary): string {
  if (!hasSuggestions(s)) return 'No watch history yet. Import a Google Takeout watch history below, and the channels in it are suggested here, most watched first.' + (s.related.sources ? ' Channels your followed ones point at are added as YouTube is asked about them.' : '')
  const watches = s.sources.reduce((n, x) => n + x.watches, 0)
  const from = !s.sources.length ? 'related channels' : s.sources.length === 1 ? `the ${s.sources[0].source} history` : `${format.count(s.sources.length, 'history', 'histories')} (${s.sources.map(x => x.source).join(', ')})`
  const out = s.sources.length ? `, out of ${format.count(watches, 'watch', 'watches')}` : ''
  const head = s.open ? `${format.count(s.open, 'channel')} from ${from} to consider${out}.` : `Every channel from ${from} has been followed or dismissed.`
  const done = [s.followed && `${format.integer(s.followed)} followed`, s.dismissed && `${format.integer(s.dismissed)} dismissed`].filter(Boolean)
  const key = s.configured ? '' : ' Following and adding need the server’s YouTube key (YOUTUBE_API_KEY).'
  const related = describeRelated(s)
  return head + (related ? ` ${related}` : '') + (done.length ? ` So far ${done.join(' and ')}.` : '') + key
}

/** What the finding says of related channels: how many open ones they point at, and how far asking YouTube has got. */
export function describeRelated(s: SuggestionSummary): string {
  const r = s.related
  if (!r.sources || (r.asked && !s.open)) return ''
  if (!r.asked) return `YouTube has not been asked yet which channels the ${format.count(r.sources, 'followed or most watched channel')} point at; the server asks every few hours.`
  const never = s.sources.length && s.unwatched ? ` (${format.integer(s.unwatched)} never watched)` : ''
  const pointed = s.sources.length ? `${format.integer(s.suggested)} of them are pointed at by related channels${never}` : `What ${format.count(r.asked, 'followed or most watched channel')} point at`
  const failed = r.failed ? ` ${format.count(r.failed, 'channel')} could not be read last time.` : ''
  return `${pointed}, asked about ${r.last ? `last on ${format.date(r.last)}` : 'this week'}.${failed}`
}

/** A suggestion's line under its title: how much and how lately it was watched. */
export function describeWatched(x: Suggestion): string {
  const parts = x.watches ? [format.count(x.watches, 'watch', 'watches'), format.count(x.videos, 'video')] : [x.pasted ? `Pasted ${format.date(x.pasted)}` : 'Never watched']
  if (x.last) parts.push(`last ${format.date(x.last)}`)
  if (x.total_videos != null) parts.push(`${format.integer(x.total_videos)} on ${x.platform === 'iplayer' ? 'iPlayer' : 'YouTube'}`)
  return parts.join(' · ')
}

/** Which of your channels point at a suggestion, the strongest first: "Pointed at by A, B and 3 more", or '' for none. */
export function describeSuggestedBy(x: Suggestion): string {
  if (!x.suggested_by) return ''
  const names = x.suggested_from.slice(0, x.suggested_by)
  const more = x.suggested_by - names.length
  if (!names.length) return `Pointed at by ${format.count(x.suggested_by, 'related channel')}`
  const list = more ? `${names.join(', ')} and ${format.integer(more)} more` : names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0]
  return `Pointed at by ${list}`
}

/** Where a suggestion sits: its group's name and YouTube's topics for it, or '' for neither. */
export function placeOf(x: Suggestion, groups: Map<number, string>): string {
  return [x.group_id === null ? undefined : groups.get(x.group_id), x.topics.join(', ')].filter(Boolean).join(' · ')
}

/** What following said: its videos come at once, or after the channels the running sync has already (it takes this one next). */
export function describeFollowed(title: string, sync: SyncJob): string {
  return sync.total > 1 ? `Following ${title}. Its videos are fetched after the ${format.count(sync.total - 1, 'channel')} the running sync has first.` : `Following ${title}. Its videos are being fetched.`
}

/** What the group select offers: each group with how many channels it holds, then the ungrouped. */
export function groupChoices(s: SuggestionSummary): { value: string; label: string }[] {
  return [
    { value: '', label: 'Every group' },
    ...s.groups.filter(g => g.channels > 0).map(g => ({ value: String(g.id), label: `${g.name} (${format.integer(g.channels)})` })),
    ...(s.ungrouped ? [{ value: 'none', label: `Not in a group (${format.integer(s.ungrouped)})` }] : []),
  ]
}

/** The filter the page's URL holds. */
export function filterOf(params: URLSearchParams): SuggestionFilter {
  return { group: params.get('group') ?? undefined, topic: params.get('topic') ?? undefined, kids: params.get('kids') ?? undefined, dismissed: params.get('view') === 'dismissed', order: params.get('order') === 'suggested' ? 'suggested' : undefined, pasted: params.get('pasted') === 'true' || undefined }
}

export function SuggestionsScreen() {
  const queryClient = useQueryClient()
  const summary = useLoad({ queryKey: keys.suggestionSummary, queryFn: api.suggestionSummary })
  const [note, setNote] = useState<string>()
  const refresh = useAsyncAction(async () => {
    const r = await api.refreshSuggestions()
    setNote(r.error ? `Regrouped, but YouTube could not be asked about the channels: ${r.error}` : undefined)
    await queryClient.invalidateQueries({ queryKey: keys.suggestions })
  }, { describeError })
  const ready = summary.status === 'ready'

  return (
    <>
      <PageHeader
        title="Suggestions"
        scope="Channels from the watch history, related channels and lists pasted in"
        finding={ready ? { text: describeSuggestions(summary.data) } : undefined}
        actions={ready && summary.data.sources.length ? (
          <AsyncButton variant="outline" phase={refresh.phase} error={refresh.error} labels={{ idle: 'Regroup', pending: 'Regrouping…', done: 'Regrouped' }} onClick={() => void refresh.run()} />
        ) : undefined}
      />
      {note && <p role="status" className="flex flex-wrap items-center gap-2 type-body-sm"><Status tone="warning">YouTube not asked</Status>{note}</p>}
      <DataView state={summary} isEmpty={s => !hasSuggestions(s)} skeleton={<ListSkeleton />} empty={<div className="grid gap-12"><PasteForm /><ImportForm first /></div>}>
        {s => (
          <div className="grid gap-12">
            <PasteForm />
            <Tabs param="view" items={views} label="Suggestions">
              {() => <Chooser summary={s} />}
            </Tabs>
            <ImportForm first={!s.sources.length} />
          </div>
        )}
      </DataView>
    </>
  )
}

/** The filters, the group's name, and the list for them. */
function Chooser({ summary }: { summary: SuggestionSummary }) {
  const [params, setParams] = useSearchParams()
  const filter = filterOf(params)
  const set = (name: string, value: string) => setParams(p => { const out = new URLSearchParams(p); if (value) out.set(name, value); else out.delete(name); return out }, { replace: true })
  const group = summary.groups.find(g => String(g.id) === filter.group)

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end gap-4">
        <Field label="Group" className="min-w-56 max-w-sm">
          <NativeSelect value={filter.group ?? ''} onChange={e => set('group', e.target.value)}>
            {groupChoices(summary).map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </NativeSelect>
        </Field>
        <Field label="Topic" className="min-w-40">
          <NativeSelect value={filter.topic ?? ''} onChange={e => set('topic', e.target.value)}>
            <option value="">Any topic</option>
            {summary.topics.map(t => <option key={t.name} value={t.name}>{`${t.name} (${format.integer(t.channels)})`}</option>)}
          </NativeSelect>
        </Field>
        <Field label="Audience" className="min-w-40">
          <NativeSelect value={filter.kids ?? ''} onChange={e => set('kids', e.target.value)}>
            <option value="">Anyone</option>
            <option value="yes">{`Made for kids (${format.integer(summary.kids)})`}</option>
            <option value="no">Not made for kids</option>
          </NativeSelect>
        </Field>
        <Field label="Show" className="min-w-40">
          <NativeSelect value={filter.pasted ? 'pasted' : ''} onChange={e => set('pasted', e.target.value ? 'true' : '')}>
            <option value="">Everything</option>
            <option value="pasted">{`Pasted in (${format.integer(summary.pasted)})`}</option>
          </NativeSelect>
        </Field>
        <Field label="Order" className="min-w-48">
          <NativeSelect value={filter.order ?? ''} onChange={e => set('order', e.target.value)}>
            <option value="">Most watched</option>
            <option value="suggested">Most pointed at by your channels</option>
          </NativeSelect>
        </Field>
      </div>
      {group && <GroupName key={group.id} group={group} />}
      <Queue filter={filter} summary={summary} />
    </div>
  )
}

/** Name the group being looked at; the name it was given by its channels until then. */
export function GroupName({ group }: { group: SuggestionGroup }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(group.named ? group.name : '')
  const rename = useAsyncAction(async () => {
    await api.renameGroup(group.id, name)
    await queryClient.invalidateQueries({ queryKey: keys.suggestionSummary })
  }, { describeError })
  const onSubmit = (e: FormEvent) => { e.preventDefault(); void rename.run() }
  return (
    <form onSubmit={onSubmit} aria-label="Name this group" className="flex max-w-xl flex-wrap items-end gap-3">
      <Field label="Name this group" hint={group.named ? 'Clear it to go back to a name made from its channels.' : `Until it is named, it goes by its top channels: ${group.name}.`} error={rename.phase === 'error' ? rename.error : undefined} className="min-w-64 flex-1">
        <Input value={name} onChange={e => setName(e.target.value)} placeholder={group.name} autoComplete="off" maxLength={80} />
      </Field>
      <AsyncButton type="submit" variant="outline" phase={rename.phase} error={rename.error} labels={{ idle: 'Save name', pending: 'Saving…', done: 'Saved' }} />
    </form>
  )
}

/** The list for a filter, worked through from the keyboard. */
function Queue({ filter, summary }: { filter: SuggestionFilter; summary: SuggestionSummary }) {
  const load = useLoad({ queryKey: keys.suggestionList(filter), queryFn: () => api.suggestions(filter) })
  return (
    <DataView
      state={load}
      isEmpty={p => p.items.length === 0}
      skeleton={<ListSkeleton />}
      empty={filter.dismissed
        ? <EmptyState title="Nothing dismissed">Channels dismissed from the list wait here, in case one is wanted after all.</EmptyState>
        : <EmptyState title="Nothing left to consider here">Every channel that matches is followed or dismissed. Choose another group or topic, or look through the dismissed ones.</EmptyState>}
    >
      {p => <Answers items={p.items} total={p.total} dismissedView={!!filter.dismissed} summary={summary} order={filter.pasted ? 'latest pasted first' : filter.order === 'suggested' ? 'most pointed at first' : 'best first'} />}
    </DataView>
  )
}

function Answers({ items, total, dismissedView, summary, order }: { items: Suggestion[]; total: number; dismissedView: boolean; summary: SuggestionSummary; order: string }) {
  const queryClient = useQueryClient()
  const undoable = useUndoable()
  const [said, setSaid] = useState<string>()
  const rows = items.filter(x => !undoable.isRemoved(x.channel_id))
  const active = useActiveItem(rows, x => x.channel_id, { noun: 'channel' })
  const groups = new Map(summary.groups.map(g => [g.id, g.name]))
  const configured = summary.configured

  const reread = async () => { for (const queryKey of [keys.suggestions, keys.channels, keys.library, keys.videos]) await queryClient.invalidateQueries({ queryKey }) }
  const follow = useAsyncAction(async (x: Suggestion) => {
    const r = await api.add(x.link)
    setSaid(describeFollowed(x.title, (r as Extract<Added, { kind: 'channel' }>).sync))     // a channel's id adds the channel
    await reread()
  }, { describeError })
  const addWatched = useAsyncAction(async (x: Suggestion) => {
    const r = await api.addWatched(x.channel_id)
    const gone = r.missing ? ` ${format.count(r.missing, 'video')} YouTube no longer has.` : ''
    setSaid(`Added ${format.count(r.added, 'video')} of ${x.title} to the library${r.already ? ` (${format.integer(r.already)} were there already)` : ''}.${gone}`)
    await reread()
  }, { describeError })

  const dismiss = (x: Suggestion) => undoable.schedule({
    id: x.channel_id,
    message: dismissedView ? `${x.title} is back on the list.` : `Dismissed ${x.title}.`,
    failure: `${x.title} is back: that did not go through.`,
    commit: async () => {
      try { await api.dismiss(x.channel_id, !dismissedView) } finally { await queryClient.invalidateQueries({ queryKey: keys.suggestions }) }
    },
  })

  const x = active.activeItem!                                    // only run while there is one: each answer is disabled without it
  const canFollow = (y: Suggestion) => configured || y.platform === 'iplayer'     // a programme needs no YouTube key
  const writing = !active.activeItem || !canFollow(active.activeItem) || dismissedView || follow.phase === 'pending' || addWatched.phase === 'pending'
  const answers: Shortcut[] = [
    { keys: ['f'], label: 'Follow', run: () => void follow.run(x), disabled: writing },
    { keys: ['a'], label: 'Add watched videos', run: () => void addWatched.run(x), disabled: writing || !active.activeItem?.watches },
    { keys: ['d'], label: dismissedView ? 'Restore' : 'Dismiss', run: () => dismiss(x), disabled: !active.activeItem },
  ]
  const shortcuts = [...active.shortcuts, ...answers]
  useHotkeys(shortcuts)
  const failure = [follow, addWatched].find(a => a.phase === 'error')

  return (
    <section aria-labelledby="channels" className="grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="channels" className="type-heading">{dismissedView ? 'Dismissed channels' : 'Channels to consider'}</h2>
        <p className="type-body-sm text-muted-foreground">{total > items.length ? `The first ${format.integer(items.length)} of ${format.integer(total)}, ${order}.` : `${format.count(total, 'channel')}, ${order}.`}</p>
      </div>
      <KeysLegend shortcuts={shortcuts} />
      {failure && <p role="alert" className="type-body-sm text-danger">{failure.error}</p>}
      {said && !failure && <p role="status" className="type-body-sm">{said}</p>}
      <ActiveList
        label={dismissedView ? `Dismissed channels, ${order}` : `Channels to consider, ${order}`}
        active={active}
        empty={<EmptyState title="That was the last one here">Choose another group or topic to keep going.</EmptyState>}
      >
        {s => (
          <div className="grid gap-2 sm:flex sm:items-start sm:gap-3">
            <div className="flex min-w-0 flex-1 items-start gap-3">
            <Thumbnail src={s.thumbnail} alt="" missing="None" className="w-12 shrink-0 rounded-full" />
            <div className="grid min-w-0 flex-1 gap-1">
              <a href={withBase(s.link)} target="_blank" rel="noreferrer" className="truncate type-body font-medium hover:underline">{s.title}</a>
              <p className="type-body-sm text-muted-foreground tabular-nums">{describeWatched(s)}</p>
              {describeSuggestedBy(s) && <p className="type-body-sm text-muted-foreground">{describeSuggestedBy(s)}</p>}
              <p className="flex flex-wrap items-center gap-2 type-caption text-muted-foreground">
                {placeOf(s, groups) && <span>{placeOf(s, groups)}</span>}
                {s.made_for_kids && <Status tone="neutral">Made for kids</Status>}
                {s.platform === 'iplayer' && <Status tone="neutral">iPlayer</Status>}
                {s.in_library && <Status tone="info">Some videos in the library</Status>}
              </p>
            </div>
            </div>
            <span className="flex flex-wrap gap-1 sm:shrink-0 sm:justify-end">
              {canFollow(s) && !dismissedView && <RowAction label="Follow" subject={s.title} onClick={() => void follow.run(s)} />}
              {configured && !dismissedView && s.watches > 0 && <RowAction label="Add watched videos" subject={s.title} onClick={() => void addWatched.run(s)} />}
              <RowAction label={dismissedView ? 'Restore' : 'Dismiss'} subject={s.title} onClick={() => dismiss(s)} />
            </span>
          </div>
        )}
      </ActiveList>
      <UndoBar undoable={undoable} />
    </section>
  )
}

/** Mirrors the list: rows with a round picture, a title and a line under it. */
function ListSkeleton() {
  return (
    <div className="grid gap-3" aria-hidden>
      {[0, 1, 2, 3, 4].map(i => (
        <div key={i} className="flex items-center gap-3 px-3 py-2">
          <Skeleton className="size-12 rounded-full" />
          <div className="grid flex-1 gap-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-3 w-1/2" /></div>
        </div>
      ))}
    </div>
  )
}

/** What a paste said: how many were found on each, which were followed already, and what named nothing. */
export function describePasted(r: Pasted): string {
  const on = (p: string) => r.found.filter(f => f.platform === p).length
  const where = [on('youtube') && `${format.integer(on('youtube'))} on YouTube`, on('iplayer') && `${format.integer(on('iplayer'))} on iPlayer`].filter(Boolean).join(' and ')
  const parts = [r.found.length ? `Added ${format.count(r.found.length, 'suggestion')} (${where}).` : 'Nothing new to suggest.']
  if (r.already.length) parts.push(`Already followed: ${r.already.map(a => a.title).join(', ')}.`)
  if (r.problems.length) parts.push(`Not found: ${r.problems.map(p => `“${p.input}” (${p.error.replace(/\.$/, '')})`).join('; ')}.`)
  return parts.join(' ')
}

/** Paste a list of channels to follow; what is found joins the list, which then shows only what was pasted. */
export function PasteForm() {
  const queryClient = useQueryClient()
  const [, setParams] = useSearchParams()
  const [text, setText] = useState('')
  const [said, setSaid] = useState<string>()
  const [problem, setProblem] = useState<string>()
  const send = useAsyncAction(async () => {
    const r = await api.pasteSuggestions(text)
    setSaid(describePasted(r))
    if (r.found.length) { setText(''); setParams(p => { const out = new URLSearchParams(p); out.set('pasted', 'true'); out.delete('view'); return out }, { replace: true }) }
    await queryClient.invalidateQueries({ queryKey: keys.suggestions })
  }, { describeError })
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const p = text.trim() ? undefined : 'Paste at least one link, @handle or name, one a line.'
    setProblem(p)
    if (!p) void send.run()
  }
  return (
    <form onSubmit={onSubmit} noValidate aria-labelledby="paste" className="grid max-w-xl gap-3">
      <h2 id="paste" className="type-heading">Paste channels to follow</h2>
      <Field label="Channels and programmes" hint="One a line: YouTube links or @handles, iPlayer programme or episode links, or names (looked up on both)." error={problem ?? (send.phase === 'error' ? send.error : undefined)}>
        <Textarea value={text} onChange={e => setText(e.target.value)} rows={4} placeholder={'https://www.youtube.com/@…\nhttps://www.bbc.co.uk/iplayer/episodes/…\nA programme name'} />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant="outline" phase={send.phase} error={send.error} labels={{ idle: 'Add to suggestions', pending: 'Looking them up…', done: 'Added' }} />
        {said && send.phase !== 'error' && <p role="status" className="type-body-sm">{said}</p>}
      </div>
    </form>
  )
}

/** Import a Takeout watch history under a name. `first`: the page's empty state, so it says what a history is for. */
export function ImportForm({ first = false }: { first?: boolean }) {
  const queryClient = useQueryClient()
  const [source, setSource] = useState('')
  const [file, setFile] = useState<File>()
  const [problem, setProblem] = useState<string>()
  const [done, setDone] = useState<string>()
  const send = useAsyncAction(async () => {
    const r = await api.importHistory(source.trim(), await file!.text())
    setDone(`Imported ${format.count(r.watches, 'watch', 'watches')} as ${r.source}, from ${format.date(r.first)} to ${format.date(r.last)}.`)
    await queryClient.invalidateQueries({ queryKey: keys.suggestions })
  }, { describeError })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const p = !file ? 'Choose the watch-history.json or watch-history.html from a Google Takeout.' : !source.trim() ? 'Name the history, say after the account it came from.' : undefined
    setProblem(p)
    if (!p) void send.run()
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-labelledby="import" className="grid max-w-xl gap-3">
      <h2 id="import" className="type-heading">{first ? 'Bring in a watch history' : 'Import another history'}</h2>
      <p className="type-body-sm text-muted-foreground">
        In Google Takeout, export “YouTube and YouTube Music” (history as JSON if offered). The file is <code>YouTube and YouTube Music/history/watch-history.json</code> or <code>.html</code>. Importing a newer export under the same name replaces the old one; what was dismissed stays dismissed.
      </p>
      <Field label="Watch history file" error={problem ?? (send.phase === 'error' ? send.error : undefined)}>
        <Input type="file" accept=".json,.html,application/json,text/html" onChange={e => setFile(e.target.files?.[0])} />
      </Field>
      <Field label="Name" hint="Say, after the account it came from.">
        <Input value={source} onChange={e => setSource(e.target.value)} placeholder="main" autoComplete="off" maxLength={64} />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant={first ? 'default' : 'outline'} phase={send.phase} error={send.error} labels={{ idle: 'Import', pending: 'Importing…', done: 'Imported' }} />
        {done && send.phase !== 'error' && <p role="status" className="type-body-sm">{done}</p>}
      </div>
    </form>
  )
}
