// The one question: "What is on the Plex server, and what of it does Tubes follow?" The finding says whether Plex is set up and
// answering (and what to do when it is not), how many libraries it has, and how much of the listing shown is followed already. Then,
// in the order a person asks next: which library and filters (the same ones Plex's own browser offers: genre, rating, a title), the
// films or shows they list, each followed with one action, and following the listing itself as a channel of its own, so whatever comes
// to match those filters later arrives by itself (src/tubes/plex.py's notes).
//
// Patterns: useLoad -> DataView for the status and for each page of the listing (TableSkeleton, an EmptyState that says to widen the
// filters); the library, filters, title and page live in the URL, so a listing can be reloaded or linked; RowAction per row ("Follow
// Harbour Lights"), shown only on rows not followed yet; one filled button (Follow as a channel). Pictures come through the server
// (/api/plex/image), never from Plex, whose address needs the token.
import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { AsyncButton, Button, DataTable, DataView, EmptyState, Field, Input, NativeSelect, PageHeader, RowAction, Status, TableSkeleton, Thumbnail, format, useAsyncAction, useLoad, type Column } from 'strata-react'
import { PLEX_PAGE, api, describeError, keys, plexParams, withBase, type Added, type PlexChoice, type PlexFilter, type PlexItem, type PlexPage, type PlexSection, type PlexStatus } from '../api'

/** The page's finding. */
export function describePlex(s: PlexStatus): string {
  if (!s.configured) return 'Plex is not set up. Put PLEX_URL (such as http://server.lan:32400) and PLEX_TOKEN in the server’s environment and restart it.'
  if (!s.reachable) return `Plex does not answer: ${s.error ?? 'no reason given'}`
  return `Plex${s.version ? ` ${s.version}` : ''} has ${format.count(s.sections.length, 'film or TV library', 'film and TV libraries')}. Follow a show or a film below, or the whole listing as a channel.`
}

/** How big a listing is and how much of the page shown is followed. */
export function describeListing(page: PlexPage): string {
  const followed = page.items.filter(i => i.followed).length
  return `${format.count(page.total, 'title')}; ${format.integer(followed)} of the ${format.integer(page.items.length)} shown ${followed === 1 ? 'is' : 'are'} followed.`
}

/** What a listing's filters say, for a channel's name: `Films: Animation, gb/U`. */
export function filterName(section: PlexSection | undefined, f: PlexFilter, genres: PlexChoice[]): string {
  const genre = genres.find(g => g.key === f.genre)?.title
  const parts = [genre, f.contentRating, f.title?.trim() ? `“${f.title.trim()}”` : undefined].filter(Boolean)
  const lib = section?.title ?? 'Plex'
  return parts.length ? `${lib}: ${parts.join(', ')}` : lib
}

/** What was followed, in a sentence. */
export function describeFollowed(a: Added): string {
  return a.kind === 'channel' ? `Following ${a.channel.title}. ${a.channel.kind === 'filter' ? 'What it lists is' : 'Its episodes are'} being added.` : `Added “${a.video.title}” to Films.`
}

/** The listing's filters, read from the URL. */
export function filterFrom(params: URLSearchParams, sections: PlexSection[]): PlexFilter {
  const section = sections.some(s => s.key === params.get('section')) ? params.get('section')! : sections[0]?.key ?? ''
  return { section, genre: params.get('genre') ?? undefined, contentRating: params.get('rating') ?? undefined, title: params.get('title') ?? undefined }
}

const subtitle = (i: PlexItem) => [i.year, i.content_rating, i.episodes != null ? format.count(i.episodes, 'episode') : undefined].filter(v => v != null && v !== '').join(' · ')

export function PlexScreen() {
  const status = useLoad({ queryKey: keys.plex, queryFn: api.plex })
  const ok = status.status === 'ready' && status.data.reachable ? status.data : undefined
  return (
    <>
      <PageHeader title="Plex" scope="Films and TV from the Plex server, read and played through Tubes" finding={status.status === 'ready' ? { text: describePlex(status.data) } : undefined} />
      <DataView
        state={status}
        isEmpty={s => !s.reachable || s.sections.length === 0}
        skeleton={<TableSkeleton rows={6} columns={3} />}
        empty={<EmptyState title={ok ? 'No film or TV libraries' : 'Plex cannot be read'}>{ok ? 'Plex has no film or TV library to list. Add one in Plex, then come back.' : 'Once the server can reach Plex, its films and shows are listed here to follow.'}</EmptyState>}
      >
        {s => <Browser sections={s.sections} />}
      </DataView>
    </>
  )
}

/** The library's listing with its filters, and following from it. Its own component, so it runs only once Plex has answered. */
export function Browser({ sections }: { sections: PlexSection[] }) {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const f = filterFrom(params, sections)
  const page = Math.max(0, Number(params.get('page') ?? 0) || 0)
  const section = sections.find(s => s.key === f.section)!     // filterFrom always names one of them (the Browser is only shown with a library)
  const genres = useLoad({ queryKey: keys.plexChoices(f.section, 'genre'), queryFn: () => api.plexChoices(f.section, 'genre'), staleTime: 300_000 })
  const ratings = useLoad({ queryKey: keys.plexChoices(f.section, 'contentRating'), queryFn: () => api.plexChoices(f.section, 'contentRating'), staleTime: 300_000 })
  const listing = useLoad({ queryKey: keys.plexBrowse(f, page), queryFn: () => api.plexBrowse(f, page) })
  const [title, setTitle] = useState(f.title ?? '')
  const [done, setDone] = useState<Added>()

  /** Change some of the URL's filters; any change starts again at the first page. */
  const set = (changes: Record<string, string | undefined>) => setParams(p => {
    const next = new URLSearchParams(p)
    for (const [k, v] of Object.entries(changes)) { if (v) next.set(k, v); else next.delete(k) }
    if (!('page' in changes)) next.delete('page')
    return next
  })

  const refresh = async () => { for (const queryKey of [keys.plex, keys.channels, keys.library, keys.videos, keys.sync]) await queryClient.invalidateQueries({ queryKey }) }
  const follow = useAsyncAction(async (i: PlexItem) => { setDone(await api.plexFollow({ key: i.key })); await refresh() }, { describeError })
  const genreList = genres.status === 'ready' ? genres.data : []

  const columns: Column<PlexItem>[] = [
    { key: 'picture', header: 'Picture', hideHeader: true, cell: i => <Thumbnail src={i.thumb ? withBase(i.thumb) : null} alt="" missing="No picture" aspect="2/3" className="w-12" /> },
    {
      key: 'title', header: 'Title', truncate: true, cell: i => (
        <span className="flex min-w-0 flex-col">
          <span className="truncate">{i.title}</span>
          <span className="truncate type-caption text-muted-foreground">{subtitle(i)}</span>
        </span>
      ),
    },
    { key: 'state', header: 'In Tubes', cell: i => (i.followed ? <Status tone="success">Followed</Status> : <span className="text-muted-foreground">–</span>) },
    { key: 'actions', header: 'Actions', hideHeader: true, cell: i => <span className="flex justify-end">{!i.followed && <RowAction label="Follow" subject={i.title} onClick={() => void follow.run(i)} />}</span> },
  ]

  const onTitle = (e: FormEvent) => { e.preventDefault(); set({ title: title.trim() || undefined }) }

  return (
    <div className="grid gap-6">
      <section aria-labelledby="listing" className="grid gap-3">
        <h2 id="listing" className="type-heading">Find</h2>
        <div className="grid max-w-4xl gap-3 sm:grid-cols-3">
          <Field label="Library">
            <NativeSelect value={f.section} onChange={e => { setTitle(''); set({ section: e.target.value, genre: undefined, rating: undefined, title: undefined }) }}>
              {sections.map(s => <option key={s.key} value={s.key}>{s.title}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Genre">
            <NativeSelect value={f.genre ?? ''} onChange={e => set({ genre: e.target.value || undefined })}>
              <option value="">Any genre</option>
              {genreList.map(g => <option key={g.key} value={g.key}>{g.title}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Rating">
            <NativeSelect value={f.contentRating ?? ''} onChange={e => set({ rating: e.target.value || undefined })}>
              <option value="">Any rating</option>
              {(ratings.status === 'ready' ? ratings.data : []).map(r => <option key={r.key} value={r.title}>{r.title}</option>)}
            </NativeSelect>
          </Field>
        </div>
        <form onSubmit={onTitle} className="flex max-w-xl flex-wrap items-end gap-3" aria-label="Title">
          <Field label="Title has" className="grow">
            <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="Any title" autoComplete="off" spellCheck={false} />
          </Field>
          <Button type="submit" variant="outline">Narrow</Button>
        </form>
      </section>

      {follow.phase === 'error' && <p role="alert" className="type-body-sm text-danger">{follow.error}</p>}
      {done && <p role="status" className="type-body-sm">{describeFollowed(done)}</p>}

      <DataView
        state={listing}
        isEmpty={p => p.items.length === 0}
        skeleton={<TableSkeleton rows={8} columns={3} />}
        empty={<EmptyState title="Nothing matches">No title in {section.title} has all of these. Choose another genre or rating, or clear the title.</EmptyState>}
      >
        {p => (
          <div className="grid gap-3">
            <p className="type-body-sm text-muted-foreground tabular-nums">{describeListing(p)}</p>
            <DataTable caption={`${section.title}, as Plex lists it`} columns={columns} rows={p.items} rowKey={i => i.key} />
            <Pages page={page} total={p.total} onPage={n => set({ page: n ? String(n) : undefined })} />
          </div>
        )}
      </DataView>

      <FollowListing filter={f} name={filterName(section, f, genreList)} onFollowed={async a => { setDone(a); await refresh() }} />
    </div>
  )
}

/** Earlier and later pages of a listing, and where this one is. */
export function Pages({ page, total, onPage }: { page: number; total: number; onPage: (n: number) => void }) {
  if (total <= PLEX_PAGE) return null
  const first = page * PLEX_PAGE + 1, last = Math.min(total, (page + 1) * PLEX_PAGE)
  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center gap-3">
      <Button size="sm" variant="outline" disabled={page === 0} onClick={() => onPage(page - 1)}>Earlier</Button>
      <span className="type-body-sm tabular-nums">{format.integer(first)}–{format.integer(last)} of {format.integer(total)}</span>
      <Button size="sm" variant="outline" disabled={last >= total} onClick={() => onPage(page + 1)}>Later</Button>
    </nav>
  )
}

/** Follow the listing itself as a channel: what matches these filters now, and whatever comes to match them. */
export function FollowListing({ filter, name, onFollowed }: { filter: PlexFilter; name: string; onFollowed: (a: Added) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const follow = useAsyncAction(async () => { await onFollowed(await api.plexFollow({ section: filter.section, params: plexParams(filter), title: title.trim() || name })); setTitle('') }, { describeError })
  return (
    <form onSubmit={e => { e.preventDefault(); void follow.run() }} aria-labelledby="follow-listing" className="grid max-w-xl gap-3">
      <h2 id="follow-listing" className="type-heading">Follow this listing</h2>
      <Field label="Channel name" hint="Everything this listing has becomes a channel of its own, and a sync adds whatever comes to match it later (and hides what stops matching)." error={follow.phase === 'error' ? follow.error : undefined}>
        <Input value={title} onChange={e => setTitle(e.target.value)} placeholder={name} autoComplete="off" />
      </Field>
      <div>
        <AsyncButton type="submit" phase={follow.phase} error={follow.error} labels={{ idle: 'Follow as a channel', pending: 'Following…', done: 'Following' }} />
      </div>
    </form>
  )
}
