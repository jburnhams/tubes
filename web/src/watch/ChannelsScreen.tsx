// The one question: "Which channels are in the library?" Every channel as a large round picture
// with its name and how many videos it has, each one link to its page. Channels are added on
// Admin’s Library page, so the empty state says so.
import { Link } from 'react-router'
import { DataView, useLoad } from 'strata-react'
import { api, keys } from '../api'
import { Avatar } from './cards'
import { countFor } from './format'
import { Nothing, trouble } from './Shown'

const grid = 'grid grid-cols-2 gap-x-6 gap-y-10 sm:grid-cols-3 lg:grid-cols-5 2xl:grid-cols-6'

export function ChannelsScreen() {
  const load = useLoad({ queryKey: keys.channels, queryFn: api.channels })
  return (
    <>
      <h1 className="mb-6 text-tube-lg font-bold">Channels</h1>
      <DataView error={trouble}
        state={load}
        isEmpty={cs => cs.length === 0}
        skeleton={<div aria-hidden className={grid}>{Array.from({ length: 10 }, (_, i) => <div key={i} className="grid justify-items-center gap-3 motion-safe:animate-pulse"><div className="aspect-square w-3/4 rounded-full bg-tube-chip" /><div className="h-4 w-1/2 rounded-tube-sm bg-tube-chip" /></div>)}</div>}
        empty={<Nothing title="No channels yet">Channels are added on Admin’s Library page, by link or @handle, and their videos follow.</Nothing>}
      >
        {cs => (
          <ul aria-label="Channels" className={grid}>
            {cs.map(c => (
              <li key={c.id}>
                <Link to={`/channels/${encodeURIComponent(c.id)}`} className="grid justify-items-center gap-3 text-center">
                  <Avatar channel={c} size="aspect-square w-3/4 text-tube-xl" />
                  <span className="grid gap-0.5">
                    <span className="text-tube-base font-medium">{c.title}</span>
                    <span className="text-tube-xs text-tube-quiet">{countFor(c)}</span>
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
