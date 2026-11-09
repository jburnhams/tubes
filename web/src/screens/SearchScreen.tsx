// The one question: "Which videos have these words in their title?" The words are in the URL
// (?q=), so a search can be linked and reloaded; the results are newest first, a page at a time.
import { useSearchParams } from 'react-router'
import { EmptyState, PageHeader } from 'strata-react'
import { SearchForm } from './parts'
import { VideoList } from './VideoList'

export function SearchScreen() {
  const [params] = useSearchParams()
  const q = (params.get('q') ?? '').trim()
  return (
    <>
      <PageHeader title="Search" scope={q ? `Titles with every word of “${q}”` : 'Titles in the library'} />
      <SearchForm key={q} initial={q} />
      {q ? (
        <VideoList
          filter={{ q }}
          label={`Videos matching “${q}”, newest first`}
          end="That is every match."
          empty={<EmptyState title="No titles match">Try fewer words, or a different spelling. Words can be in any order.</EmptyState>}
        />
      ) : (
        <EmptyState title="Search the titles">Type a word or two from a title. Every word has to appear, in any order.</EmptyState>
      )}
    </>
  )
}
