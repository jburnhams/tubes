// The one question: "Can this server fetch and play, and is the library fresh?" The finding names
// the first thing that is wrong (a missing tool, no YouTube key, an empty library, a nearly full disk) or
// says all is well. Then, in the order a person checks: the library (managed on the Library page),
// the tools a fetch needs (Status words, never colour alone), the disk
// the cache is on (a Meter with named thresholds), and what is being fetched now. The read is
// polled; a poll that fails keeps the last readings and says how old they are.
import { DataView, EmptyState, LinkCard, LinkCardList, Meter, PageHeader, Skeleton, StaleNotice, Status, crossedThreshold, format, useLoad, type MeterThreshold } from 'strata-react'
import { api, keys, paths, withBase, type SystemStatus } from '../api'

/** One set of thresholds for the cache's disk, as shares of its size. */
export const diskThresholds: MeterThreshold[] = [
  { at: 0.9, tone: 'warning', label: 'Filling up' },
  { at: 0.97, tone: 'danger', label: 'Nearly full' },
]

/** The disk's usable size, as `df` counts it: what is used plus what is free. */
export const usable = (disk: SystemStatus['disk']) => disk.used + disk.free

/** The page's finding: the first problem, in the order it stops things working, else that all is well. */
export function describeSystem(s: SystemStatus, answering = true): string {
  if (!answering) return 'The server is not answering. The readings below are from its last answer.'
  if (!s.can_fetch) return 'This server cannot fetch videos: fetching needs Linux or macOS. Cached copies still play.'
  if (!s.ytdlp) return 'yt-dlp is missing, so nothing new can be fetched. Install it, or set its path in Settings.'
  if (!s.ffmpeg) return 'ffmpeg is missing, so nothing new can be fetched. Install it, or set its path in Settings.'
  if (!s.library.configured) return 'The library cannot be added to or synced: the server has no YouTube key. Put YOUTUBE_API_KEY in its environment and restart it.'
  if (!s.library.channels) return 'The library is empty. Add a channel on the Library page.'
  const crossed = crossedThreshold(s.disk.used / usable(s.disk), diskThresholds)
  if (crossed?.tone === 'danger') return `The cache’s disk is nearly full, with ${format.bytes(s.disk.free)} free. Lower the cache limit or free space on it.`
  return `Everything is ready. ${s.library.synced ? `The library was last synced on ${format.dateTime(s.library.synced)}` : 'The library has not had a full sync yet'}, and the cache’s disk has ${format.bytes(s.disk.free)} free.`
}

function SystemSkeleton() {
  return (
    <div className="grid gap-10" aria-hidden>
      <Skeleton className="h-24 w-full max-w-xl" />
      <Skeleton className="h-32 w-full max-w-xl" />
      <Skeleton className="h-16 w-full max-w-xl" />
    </div>
  )
}

function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid max-w-xl gap-2 type-body-sm">
      {rows.map(([term, value]) => (
        <div key={term} className="flex gap-6">
          <dt className="w-28 shrink-0 text-muted-foreground">{term}</dt>
          <dd className="min-w-0 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

const tool = (version: string | null) => (version ? <span className="flex flex-wrap items-center gap-2"><Status tone="success">Found</Status><span className="tabular-nums">{version.split(' Copyright')[0]}</span></span> : <Status tone="danger">Missing</Status>)

export function SystemScreen() {
  const load = useLoad({ queryKey: keys.system, queryFn: api.system, refetchInterval: 60_000 })
  const answering = !(load.status === 'ready' && load.stale)

  return (
    <>
      <PageHeader title="System" scope="This server, checked every minute" finding={load.status === 'ready' ? { text: describeSystem(load.data, answering) } : undefined} />
      <DataView
        state={load}
        isEmpty={() => false}
        skeleton={<SystemSkeleton />}
        staleNotice={stale => <StaleNotice stale={stale} shown={when => `These readings are from ${when}.`} />}
        empty={<EmptyState title="No readings">The server sent nothing to report.</EmptyState>}
      >
        {s => (
          <div className="grid gap-10">
            <section aria-labelledby="library" className="grid gap-3">
              <h2 id="library" className="type-heading">Library</h2>
              <p className="max-w-xl type-body-sm text-muted-foreground">Channels are added on the Library page and their videos fetched from YouTube; the server syncs every followed channel every few hours.</p>
              <Facts rows={[
                ['Last synced', s.library.synced ? format.dateTime(s.library.synced) : 'Never'],
                ['Holds', <span className="tabular-nums">{format.count(s.library.videos, 'video')} from {format.count(s.library.channels, 'channel')}</span>],
                ['YouTube key', s.library.configured ? <Status tone="success">Set</Status> : <Status tone="warning">Not set</Status>],
              ]} />
            </section>

            <section aria-labelledby="tools" className="grid gap-3">
              <h2 id="tools" className="type-heading">Fetching</h2>
              <Facts rows={[
                ['yt-dlp', tool(s.ytdlp)],
                ['ffmpeg', tool(s.ffmpeg)],
                ['This system', s.can_fetch ? <Status tone="success">Can fetch</Status> : <Status tone="danger">Cannot fetch</Status>],
                ['Now', s.fetching.length ? <span className="tabular-nums">{format.count(s.fetching.length, 'video')}</span> : 'Nothing'],
              ]} />
            </section>

            <section aria-labelledby="disk" className="grid max-w-xl gap-3">
              <h2 id="disk" className="type-heading">Cache disk</h2>
              <p className="type-body-sm text-muted-foreground">The cache folder, <span className="font-mono text-foreground">{s.cache_dir}</span>, is on this disk.</p>
              <Meter label="Cache disk space used" value={s.disk.used} max={usable(s.disk)} thresholds={diskThresholds} detail={`${format.bytes(s.disk.used, format.byteUnit(usable(s.disk)))} of ${format.bytes(usable(s.disk))}`} />
            </section>

            <section aria-labelledby="running" className="grid gap-3">
              <h2 id="running" className="type-heading">Server</h2>
              <Facts rows={[
                ['Answering', answering ? <Status tone="success">Answering</Status> : <Status tone="danger">Not answering</Status>],
                ['Version', <span className="tabular-nums">{s.version}</span>],
                ['Python', <span className="tabular-nums">{s.python}</span>],
                ['Platform', s.platform],
                ['Data folder', <span className="font-mono">{s.data_dir}</span>],
              ]} />
            </section>

            <section aria-labelledby="next" className="grid gap-3">
              <h2 id="next" className="type-heading">Go to</h2>
              <LinkCardList label="Places to go from here">
                <LinkCard to="/admin/library" title="Library" description="The channels followed, adding a channel or a video, and Sync." />
                <LinkCard to="/admin/cache" title="Cache" description="What is saved, what goes first when it fills, and Trim now." />
                <LinkCard to="/admin/quota" title="YouTube quota" description="How much of the key’s daily quota is used and left, and what used it." />
                <LinkCard to="/admin/settings" title="Settings" description="The cache limit and folder, quality, signing in, the tools' paths." />
                <LinkCard href={withBase('/api/docs')} title="API reference" description="Every endpoint the server answers, with a form to try each one." />
                <LinkCard href={withBase(paths.health)} title="Health check" description="The JSON a monitor polls to see that the server is up." />
              </LinkCardList>
            </section>
          </div>
        )}
      </DataView>
    </>
  )
}
