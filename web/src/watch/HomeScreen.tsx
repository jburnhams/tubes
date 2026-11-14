// The one question: "What is there to watch?" As on the old Tubes home: a row of chips (all, then
// each channel) over a grid of the newest videos in the library, read a page at a time as the page
// scrolls. Before the library has any videos, it says where to add a channel.
// Above the grid, Continue watching: the videos part watched lately (src/tubes/viewing.py), the last
// played first, each with how far it got; a play from there picks up where it stopped. With none,
// the row is not there at all.
import { Link } from 'react-router'
import { useLoad } from 'strata-react'
import { api, keys } from '../api'
import { GridSkeleton, More, VideoCard, VideoGrid, useChannelsById } from './cards'
import { FromHere, fromState } from './from'
import { Nothing, Shown } from './Shown'
import { useVideos } from './useVideos'

function Chips() {
  const channels = useLoad({ queryKey: keys.channels, queryFn: api.channels })
  const chip = 'shrink-0 rounded-tube-sm px-3 py-1.5 text-tube-sm font-medium'
  return (
    <nav aria-label="Channels" className="-mt-2 mb-6 flex gap-3 overflow-x-auto pb-1">
      <span aria-current="page" className={`${chip} bg-tube-ink text-tube-page`}>All</span>
      {channels.status === 'ready' && channels.data.map((c, i) => <Link key={c.id} to={`/channels/${encodeURIComponent(c.id)}`} state={fromState({ source: 'chips' }, i)} className={`${chip} bg-tube-chip text-tube-ink hover:bg-tube-chip-hover`}>{c.title}</Link>)}
    </nav>
  )
}

/** The part-watched videos as one row that scrolls sideways, so it never pushes the newest far down. */
export function ContinueWatching() {
  const load = useLoad({ queryKey: keys.continueWatching, queryFn: () => api.continueWatching() })
  const byId = useChannelsById()
  return (
    <Shown state={load} skeleton={null} isEmpty={vs => vs.length === 0}>
      {vs => (
        <section aria-labelledby="continue" className="mb-10 grid gap-4">
          <h2 id="continue" className="text-tube-lg font-bold">Continue watching</h2>
          <FromHere source="continue">
            <ul aria-label="Continue watching" className="flex gap-4 overflow-x-auto pb-2">
              {vs.map((v, i) => <VideoCard key={v.id} v={v} channel={byId.get(v.channel_id)} rank={i} className="w-72 shrink-0" />)}
            </ul>
          </FromHere>
        </section>
      )}
    </Shown>
  )
}

export function HomeScreen() {
  const list = useVideos({})
  return (
    <>
      <h1 className="sr-only">Home</h1>
      <Chips />
      <ContinueWatching />
      <FromHere source="home">
        <Shown
          state={list}
          skeleton={<GridSkeleton />}
          isEmpty={vs => vs.length === 0}
          empty={<Nothing title="No videos yet">Videos appear here once a channel is in the library. <Link to="/admin/library" className="text-tube-focus">Add one in Admin</Link>.</Nothing>}
        >
          {vs => <><VideoGrid videos={vs} label="Newest videos" /><More list={list} skeleton={<GridSkeleton cards={4} />} /></>}
        </Shown>
      </FromHere>
    </>
  )
}
