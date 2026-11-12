// The one question: "Which videos have these words in their title?" The words are in the URL
// (?q=), so a search can be linked and reloaded. Results are wide rows, newest first, a page at a time.
import { useSearchParams } from 'react-router'
import { More, RowsSkeleton, VideoRow, useChannelsById } from './cards'
import { FromHere } from './from'
import { Nothing, Shown } from './Shown'
import { useVideos } from './useVideos'

function Results({ q }: { q: string }) {
  const list = useVideos({ q })
  const byId = useChannelsById()
  return (
    <Shown state={list} skeleton={<RowsSkeleton />} isEmpty={vs => vs.length === 0} empty={<Nothing title="No titles match">Try fewer words, or a different spelling. Words can be in any order.</Nothing>}>
      {vs => (
        <>
          <ul aria-label={`Videos matching “${q}”`} className="grid gap-4">{vs.map((v, i) => <VideoRow key={v.id} v={v} channel={byId.get(v.channel_id)} rank={i} />)}</ul>
          <More list={list} skeleton={<RowsSkeleton rows={2} />} />
        </>
      )}
    </Shown>
  )
}

export function SearchScreen() {
  const [params] = useSearchParams()
  const q = (params.get('q') ?? '').trim()
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="sr-only">{q ? `Search: ${q}` : 'Search'}</h1>
      {q ? <FromHere source="search" detail={q}><Results key={q} q={q} /></FromHere> : <Nothing title="Search the titles">Type a word or two from a title in the box at the top. Every word has to appear, in any order.</Nothing>}
    </div>
  )
}
