// How much of a video was seen, reported to the server as it plays (src/tubes/viewing.py turns it into
// none, short, partial or full, and Continue watching is made from it).
//
// Seen seconds are counted once each: a second counts when the playhead passes it by playing (steps of up
// to MAX_STEP seconds between two `timeupdate`s; a seek is a jump and counts nothing), so going back over a
// part does not add to it and jumping to the end does not finish a video. A part the player skips (a
// sponsor read, an intro) counts as seen: the person chose not to sit through it, which is not leaving.
//
// The page reports every REPORT_MS while it plays, when it pauses or ends, when the tab is hidden and when
// the page is left (the request is sent with keepalive, so it survives the page closing). Reports are
// cheap and the server only moves `watched` up, so a report too many does no harm; a failed one is
// dropped, as the next carries everything again.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, type RefObject } from 'react'
import { api, keys } from '../api'

/** The longest step between two time updates that still counts as playing (a 2x speed, a slow tab). */
export const MAX_STEP = 2
/** How often a playing video reports. */
export const REPORT_MS = 15_000

/** The seconds of a video seen, each counted once. */
export class Seen {
  private seconds = new Set<number>()
  private last: number | null = null

  /** The playhead is at `t` while playing: the seconds since the last place count if it got here by playing. */
  advance(t: number) {
    if (this.last !== null && t >= this.last && t - this.last <= MAX_STEP) this.mark(this.last, t)
    this.last = t
  }

  /** The playhead jumped to `t` (a seek, a skip): the next step starts there. */
  jump(t: number) {
    this.last = t
  }

  /** Count every whole second from `from` up to `to`. */
  mark(from: number, to: number) {
    for (let s = Math.max(0, Math.floor(from)); s < Math.floor(to); s++) this.seconds.add(s)
  }

  /** At the end, the last part second counts too. */
  finish(duration: number) {
    if (this.last !== null && duration - this.last <= MAX_STEP) this.mark(this.last, Math.ceil(duration))
    this.last = duration
  }

  get watched(): number {
    return this.seconds.size
  }
}

const finite = (n: number) => (Number.isFinite(n) && n > 0 ? n : null)

/**
 * Reports the play `playId` of the video in `ref` (see the file's notes). Returns the `Seen` it counts with,
 * so the player can mark the parts it skips.
 */
export function useWatchReport(ref: RefObject<HTMLVideoElement | null>, playId: number): Seen {
  const seen = useRef(new Seen()).current
  const queryClient = useQueryClient()
  useEffect(() => {
    const video = ref.current!                                             // the effect runs once the <video> is in the page
    let sent = 0, sentAt = video.currentTime
    const send = (refresh = false) => {
      const position = video.currentTime
      const continued = () => { if (refresh) void queryClient.invalidateQueries({ queryKey: keys.continueWatching }) }
      if (seen.watched === sent && position === sentAt) return continued()                   // nothing new to say
      sent = seen.watched; sentAt = position
      void api.progress(playId, { position, watched: seen.watched, length: finite(video.duration) }).then(continued, () => undefined)
    }
    const onTime = () => { if (!video.paused && !video.seeking) seen.advance(video.currentTime) }
    const onSeeking = () => seen.jump(video.currentTime)
    const onPause = () => send()
    const onEnded = () => { seen.finish(video.duration); send(true) }
    const onHidden = () => { if (document.visibilityState === 'hidden') send() }
    const onLeave = () => send()
    video.addEventListener('timeupdate', onTime)
    video.addEventListener('seeking', onSeeking)
    video.addEventListener('pause', onPause)
    video.addEventListener('ended', onEnded)
    document.addEventListener('visibilitychange', onHidden)
    window.addEventListener('pagehide', onLeave)
    const timer = setInterval(() => { if (!video.paused) send() }, REPORT_MS)
    return () => {
      clearInterval(timer)
      video.removeEventListener('timeupdate', onTime)
      video.removeEventListener('seeking', onSeeking)
      video.removeEventListener('pause', onPause)
      video.removeEventListener('ended', onEnded)
      document.removeEventListener('visibilitychange', onHidden)
      window.removeEventListener('pagehide', onLeave)
      send(true)                                                          // leaving the page: Continue watching is read again
    }
  }, [ref, playId, seen, queryClient])
  return seen
}
