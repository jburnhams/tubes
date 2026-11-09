// The one question: "What has this channel made?" Its videos, newest first, a page at a time. The
// channel itself is read first, for the title and the finding; a channel the library no longer has
// (an old link) says so, with the way back.
import { Link, useParams } from 'react-router'
import { Button, DataView, EmptyState, HttpError, PageHeader, Skeleton, describeHttpError, format, useLoad } from 'strata-react'
import { api, keys, type Channel } from '../api'
import { VideoList } from './VideoList'

export function describeChannel(c: Channel): string {
  return c.latest ? `${format.count(c.videos, 'video')}, the newest from ${format.date(c.latest)}.` : 'No videos from this channel have been copied yet.'
}

export function ChannelScreen() {
  const { id = '' } = useParams()
  const load = useLoad({
    queryKey: keys.channel(id), queryFn: () => api.channel(id),
    describeError: e => (e instanceof HttpError && e.status === 404 ? 'The library has no such channel. It may have been removed since the link was made.' : describeHttpError(e)),
  })
  return (
    <DataView
      state={load}
      isEmpty={() => false}
      skeleton={<div className="grid gap-3" aria-hidden><Skeleton className="h-9 w-64" /><Skeleton className="h-5 w-96 max-w-full" /></div>}
      empty={null}
    >
      {c => (
        <>
          <PageHeader title={c.title} scope={c.handle ?? 'Channel'} finding={{ text: describeChannel(c) }} actions={<Button asChild variant="outline" size="sm"><Link to="/channels">All channels</Link></Button>} />
          <VideoList
            filter={{ channel: c.id }}
            withChannel={false}
            label={`Videos from ${c.title}, newest first`}
            end={`That is every video from ${c.title}.`}
            empty={<EmptyState title="No videos yet">The library has this channel but none of its videos. They arrive with the library's next sync of the channel.</EmptyState>}
          />
        </>
      )}
    </DataView>
  )
}
