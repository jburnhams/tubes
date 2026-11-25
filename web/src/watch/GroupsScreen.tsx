// The one question: "Which groups of videos are there?" Every group as a picture with its name and how many
// videos it has, largest first, each one link to its page. The picture is one of the videos that represent the
// group best, picked by the server on every read (src/tubes/groups.py): so each opening of the page reads
// again (gcTime 0) and the pictures change, but nothing changes while the page is open (staleTime Infinity).
import { Link } from 'react-router'
import { DataView, Thumbnail, useLoad } from 'strata-react'
import { api, keys, type VideoGroup } from '../api'
import { gridClass } from './cards'
import { videoCount } from './format'
import { fallbackThumbnail, isPlaceholder, reportMissing } from './missing'
import { Nothing, trouble } from './Shown'

/** A group's picture: its video's thumbnail, or plain grey when none of its best videos has one. */
export function GroupPicture({ g, className = '' }: { g: VideoGroup; className?: string }) {
  const src = g.thumbnail ? [g.thumbnail, fallbackThumbnail(g.thumbnail)].filter((s): s is string => !!s) : null
  return (
    <Thumbnail src={src} alt="" aspect="16/9" eager className={`block rounded-tube ${className}`} fallback={<span className="block size-full bg-tube-chip" />}
      onLoad={img => !isPlaceholder(img)} onMissing={() => { if (g.thumbnail_video) reportMissing(g.thumbnail_video) }} />
  )
}

export function GroupsScreen() {
  const load = useLoad({ queryKey: keys.groups, queryFn: api.groups, staleTime: Infinity, gcTime: 0 })
  return (
    <>
      <h1 className="mb-6 text-tube-lg font-bold">Groups</h1>
      <DataView error={trouble}
        state={load}
        isEmpty={gs => gs.length === 0}
        skeleton={<div aria-hidden className={gridClass}>{Array.from({ length: 12 }, (_, i) => <div key={i} className="grid gap-3 motion-safe:animate-pulse"><div className="aspect-video rounded-tube bg-tube-chip" /><div className="grid gap-2"><div className="h-4 w-1/2 rounded-tube-sm bg-tube-chip" /><div className="h-3 w-1/4 rounded-tube-sm bg-tube-chip" /></div></div>)}</div>}
        empty={<Nothing title="No groups yet">Videos that belong together, whichever channel they are from, appear here once groups are loaded on the server.</Nothing>}
      >
        {gs => (
          <ul aria-label="Groups" className={gridClass}>
            {gs.map(g => (
              <li key={g.id}>
                <Link to={`/groups/${g.id}`} className="grid content-start gap-3">
                  <GroupPicture g={g} />
                  <span className="grid gap-0.5">
                    <span className="text-tube-base font-medium text-tube-ink">{g.name}</span>
                    <span className="text-tube-sm text-tube-quiet">{videoCount(g.videos)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </DataView>
    </>
  )
}
