// The one question: "What is there to watch?" The finding says how big the library copy is and how
// fresh, or, before the first sync, where to make one. Then the next questions in order: find
// something by its title (the search form, the view's one filled button), or be offered something
// (a shuffled handful, with Shuffle for another). Channels have their own screen.
import { useQueryClient } from '@tanstack/react-query'
import { Shuffle } from 'lucide-react'
import { Link } from 'react-router'
import { Button, DataView, EmptyState, PageHeader, format, useLoad } from 'strata-react'
import { api, keys, type LibraryStatus } from '../api'
import { GridSkeleton, SearchForm, VideoGrid } from './parts'

/** How many videos the shuffle offers. */
export const SHUFFLE_COUNT = 12

/** The page's finding, from the library copy. */
export function describeLibrary(l: LibraryStatus): string {
  if (!l.synced) return 'Nothing has been copied from the library yet. Sync it from the System page.'
  return `${format.count(l.videos, 'video')} from ${format.count(l.channels, 'channel')}, copied from the library on ${format.dateTime(l.synced)}.`
}

export function BrowseScreen() {
  const library = useLoad({ queryKey: keys.library, queryFn: api.library })
  const pick = useLoad({ queryKey: keys.shuffle, queryFn: () => api.shuffle(SHUFFLE_COUNT) })
  const queryClient = useQueryClient()
  const neverSynced = library.status === 'ready' && !library.data.synced

  return (
    <>
      <PageHeader
        title="Browse"
        scope="The library, as last copied"
        finding={library.status === 'ready' ? { text: describeLibrary(library.data), action: neverSynced ? <Button asChild variant="outline" size="sm"><Link to="/system">Go to System</Link></Button> : undefined } : undefined}
      />
      <SearchForm />
      <section aria-labelledby="offer" className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 id="offer" className="type-heading">Something to watch</h2>
          <Button variant="outline" size="sm" onClick={() => void queryClient.invalidateQueries({ queryKey: keys.shuffle })}>
            <Shuffle aria-hidden className="size-4" /> Shuffle
          </Button>
        </div>
        <DataView
          state={pick}
          isEmpty={vs => vs.length === 0}
          skeleton={<GridSkeleton cards={SHUFFLE_COUNT} />}
          empty={<EmptyState title="No videos yet">Videos appear here once the library has been copied. Channels are added in the library itself; a sync on the System page brings them here.</EmptyState>}
        >
          {vs => <VideoGrid videos={vs} label="Videos picked at random" />}
        </DataView>
      </section>
    </>
  )
}
