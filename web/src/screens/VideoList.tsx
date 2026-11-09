// A long list of videos, newest first, read a page at a time the Strata way: useInfiniteLoad over
// the server's cursor (the date and id of the last video held, never an offset, so a sync that
// adds videos between pages cannot make the next page repeat or skip one) -> InfiniteList, which
// asks for the next page as the end comes near, with a skeleton for it, a Try again row when it
// fails and a Show more button for the keyboard. Used by a channel's page and by search.
// InfiniteList is always its own scroll box (480px by default); 720 shows about seven rows, a
// screenful on the 4K screen it is watched on, so the box rarely needs scrolling before a page ends.
import type { ReactNode } from 'react'
import { InfiniteList, useInfiniteLoad } from 'strata-react'
import { api, cursorOf, keys, type Video, type VideoFilter, type VideoPage } from '../api'
import { RowsSkeleton, VideoRow } from './parts'

export function VideoList({ filter, label, empty, end, withChannel = true }: { filter: VideoFilter; label: string; empty: ReactNode; end: string; withChannel?: boolean }) {
  const list = useInfiniteLoad<Video, VideoPage, string>({
    queryKey: keys.list(filter),
    queryFn: ({ cursor, signal }) => api.videos(filter, cursor, signal),
    items: page => page.videos,
    itemKey: v => v.id,
    cursorAfter: cursorOf,
    hasMore: page => page.has_more,
  })
  return (
    <InfiniteList state={list} label={label} moreLabel="Show older videos" skeleton={<RowsSkeleton rows={6} />} moreSkeleton={<RowsSkeleton />} empty={empty} end={end} estimateSize={106} height={720}>
      {v => <VideoRow v={v} withChannel={withChannel} />}
    </InfiniteList>
  )
}
