// A paged read of the library's videos, newest first, over the server's cursor (the date and id of
// the last video held, never an offset, so a sync between pages cannot repeat or skip one).
import { useInfiniteLoad } from 'strata-react'
import { api, cursorOf, keys, type Video, type VideoFilter, type VideoPage } from '../api'

export function useVideos(filter: VideoFilter) {
  return useInfiniteLoad<Video, VideoPage, string>({
    queryKey: keys.list(filter),
    queryFn: ({ cursor, signal }) => api.videos(filter, cursor, signal),
    items: page => page.videos,
    itemKey: v => v.id,
    cursorAfter: cursorOf,
    hasMore: page => page.has_more,
  })
}
