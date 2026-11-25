// The one question: "What is in this group?" Its name and how many videos it has, over a grid of them, those that
// represent it best first (so the videos that picture it on the Groups page are at the top), a page at a time, each with its channel (a group gathers videos from many). A group that went (the
// groups were loaded again without it) says so.
import { useParams } from 'react-router'
import { DataView, HttpError, describeHttpError, useLoad } from 'strata-react'
import { api, keys, type VideoGroup } from '../api'
import { GridSkeleton, More, VideoGrid } from './cards'
import { videoCount } from './format'
import { FromHere } from './from'
import { Nothing, trouble } from './Shown'
import { useVideos } from './useVideos'

function Videos({ g }: { g: VideoGroup }) {
  const list = useVideos({ group: String(g.id) })
  return (
    <DataView error={trouble} state={list} skeleton={<GridSkeleton cards={8} />} isEmpty={vs => vs.length === 0} empty={<Nothing title="Nothing to watch here just now">Every video in this group is hidden: gone, not offered here, or left out by the settings.</Nothing>}>
      {vs => <><VideoGrid videos={vs} label={`Videos in ${g.name}`} /><More list={list} skeleton={<GridSkeleton cards={4} />} /></>}
    </DataView>
  )
}

export function GroupScreen() {
  const { id = '' } = useParams()
  const load = useLoad({
    queryKey: keys.group(id), queryFn: () => api.group(id),
    describeError: e => (e instanceof HttpError && (e.status === 404 || e.status === 422) ? 'There is no such group. Groups change as the library does, so it may have gone since the link was made.' : describeHttpError(e)),
  })
  return (
    <div className="mx-auto max-w-screen-2xl">
      <DataView error={trouble} state={load} isEmpty={() => false} empty={null} skeleton={<div aria-hidden className="grid gap-3 py-4 motion-safe:animate-pulse"><div className="h-8 w-64 rounded-tube-sm bg-tube-chip" /><div className="h-4 w-32 rounded-tube-sm bg-tube-chip" /></div>}>
        {g => (
          <>
            <header className="mb-6 grid gap-2 border-b border-tube-line py-4">
              <h1 className="text-tube-lg font-bold sm:text-tube-xl">{g.name}</h1>
              <p className="text-tube-sm text-tube-quiet">{videoCount(g.videos)}</p>
            </header>
            <FromHere source="group" detail={String(g.id)}><Videos g={g} /></FromHere>
          </>
        )}
      </DataView>
    </div>
  )
}
