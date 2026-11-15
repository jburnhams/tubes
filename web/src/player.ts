// Attaching an HLS stream to a <video>. The server writes each copy as HLS (fMP4 segments under a
// playlist that grows while the fetch runs, src/tubes/fetcher.py), and the only browser target is
// the latest Chrome, which plays it through Media Source Extensions with hls.js.
//
// The engine is strata-react's (`strata-react/hls`): hls.js where Media Source exists, the element's
// own HLS where it does not, up to three quiet recoveries from a dropped connection or a decoder
// hiccup, and Try again restarting where playback had reached. WatchScreen hands it to Strata's
// `MediaPlayer` as `attach`.
//
// The playlist is an EVENT playlist without an end until the fetch finishes, which hls.js treats as live; the attacher
// starts a `growing` source at its beginning (strata-react issue #208), which is what a video wants.
//
// A play that picks up where the last one stopped (Continue watching) starts there instead: MediaPlayer
// has no start time of its own, so `startingAt` hands the attacher's first load that place; the watch
// page only gives one when that part is already on the server.
import Hls from 'hls.js'
import type { SourceAttacher } from 'strata-react'
import { createHlsAttacher } from 'strata-react/hls'

/** What WatchScreen plays its stream through. */
export const attachStream = createHlsAttacher(Hls, { config: { lowLatencyMode: false } })

/** `attach` with its first load starting at `from` seconds (where the last play stopped); a restart at a time reached keeps that time. */
export function startingAt(attach: SourceAttacher, from: number): SourceAttacher {
  return (el, src, context) => attach(el, src, { ...context, startAt: context.startAt > 0 ? context.startAt : from })
}
