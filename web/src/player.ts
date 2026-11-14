// Attaching an HLS stream to a <video>. The server writes each copy as HLS (fMP4 segments under a
// playlist that grows while the fetch runs, src/tubes/fetcher.py), and the only browser target is
// the latest Chrome, which plays it through Media Source Extensions with hls.js.
//
// The engine is strata-react's (`strata-react/hls`): hls.js where Media Source exists, the element's
// own HLS where it does not, up to three quiet recoveries from a dropped connection or a decoder
// hiccup, and Try again restarting where playback had reached. WatchScreen hands it to Strata's
// `MediaPlayer` as `attach`.
//
// One thing is set here. The playlist is an EVENT playlist without an end until the fetch finishes,
// which hls.js treats as live and starts near its newest segment; a video should start at its
// beginning. strata-react's attacher starts a first load at -1 (hls.js's "choose for me") whatever
// `config.startPosition` says, so the engine handed to it turns that -1 into 0. A restart in place
// (Try again, at the time reached) passes through unchanged.
//
// A play that picks up where the last one stopped (Continue watching) starts there instead: MediaPlayer
// has no start time of its own, so `startingAt` hands the attacher's first load that place; the watch
// page only gives one when that part is already on the server.
import Hls from 'hls.js'
import type { SourceAttacher } from 'strata-react'
import { createHlsAttacher, type HlsEngine } from 'strata-react/hls'

/** The engine with a first load starting at the beginning, not the live edge. */
export function fromTheStart(Engine: HlsEngine): HlsEngine {
  return class extends Engine {
    constructor(config: ConstructorParameters<HlsEngine>[0] = {}) {
      super({ ...config, startPosition: config.startPosition === undefined || config.startPosition < 0 ? 0 : config.startPosition })
    }
  } as HlsEngine
}

/** What WatchScreen plays its stream through. */
export const attachStream = createHlsAttacher(fromTheStart(Hls), { config: { lowLatencyMode: false } })

/** `attach` with its first load starting at `from` seconds (where the last play stopped); a restart at a time reached keeps that time. */
export function startingAt(attach: SourceAttacher, from: number): SourceAttacher {
  return (el, src, context) => attach(el, src, { ...context, startAt: context.startAt > 0 ? context.startAt : from })
}
