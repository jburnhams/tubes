// The one question: "What is there to watch?" As on the old Tubes home: a row of chips (all, then
// each channel) over a grid of the newest videos in the library, read a page at a time as the page
// scrolls. Before the library has any videos, it says where to add a channel.
import { Link } from 'react-router'
import { DataView, useLoad } from 'strata-react'
import { api, keys } from '../api'
import { GridSkeleton, More, VideoGrid } from './cards'
import { Nothing, trouble } from './Shown'
import { useVideos } from './useVideos'

function Chips() {
  const channels = useLoad({ queryKey: keys.channels, queryFn: api.channels })
  const chip = 'shrink-0 rounded-tube-sm px-3 py-1.5 text-tube-sm font-medium'
  return (
    <nav aria-label="Channels" className="-mt-2 mb-6 flex gap-3 overflow-x-auto pb-1">
      <span aria-current="page" className={`${chip} bg-tube-ink text-tube-page`}>All</span>
      {channels.status === 'ready' && channels.data.map(c => <Link key={c.id} to={`/channels/${encodeURIComponent(c.id)}`} className={`${chip} bg-tube-chip text-tube-ink hover:bg-tube-chip-hover`}>{c.title}</Link>)}
    </nav>
  )
}

export function HomeScreen() {
  const list = useVideos({})
  return (
    <>
      <h1 className="sr-only">Home</h1>
      <Chips />
      <DataView error={trouble}
        state={list}
        skeleton={<GridSkeleton />}
        isEmpty={vs => vs.length === 0}
        empty={<Nothing title="No videos yet">Videos appear here once a channel is in the library. <Link to="/admin/library" className="text-tube-focus">Add one in Admin</Link>.</Nothing>}
      >
        {vs => <><VideoGrid videos={vs} label="Newest videos" /><More list={list} skeleton={<GridSkeleton cards={4} />} /></>}
      </DataView>
    </>
  )
}
