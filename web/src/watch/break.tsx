// Breaks: every so often the Watch page pauses the video and shows another page over it, such as a short
// game, until that page says it is done. Tubes knows nothing of the page: Admin > Settings > Breaks gives a
// link (an http(s) link or a path on this server), the minutes of playing between breaks and the longest a
// break lasts (settings break_*, read through GET /api/break).
//
// - The clock counts seconds of playing, not of the page being open: a paused video, a menu left open or a
//   seek adds nothing (the same rule as progress.ts: steps of up to MAX_STEP between two `timeupdate`s). It
//   is kept in this browser across videos and reloads (localStorage), so moving between short videos does
//   not put a break off; each screen that watches gets its own. It starts again from 0 after each break.
// - The break is drawn in the player's `overlay`, the picture's own box, so it is the size of the video and
//   stays in full screen. While it is up the video is paused, and a play from the controls or the keys is
//   paused again at once.
// - The page ends it with `window.parent.postMessage({ type: 'tubes:done' }, '*')`. Only a message from the
//   frame itself, from the origin of the configured link, counts. There is no close button, or a break would
//   be one tap from skipped; the time limit ends a break whose page never says so (it failed to load, the
//   server it is on is down), so a broken page cannot hold the video for good.
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import type { Break } from '../api'
import { MAX_STEP } from './progress'

/** Where this browser keeps the seconds played since the last break. */
export const PLAYED_KEY = 'tubes.break.played'
/** The message a break's page sends its parent when it is done. */
export const DONE = 'tubes:done'

/** The seconds played since the last break, as this browser kept them (0 when it kept none, or cannot keep any). */
export function readPlayed(): number {
  try {
    const n = Number(localStorage.getItem(PLAYED_KEY))
    return Number.isFinite(n) && n > 0 ? n : 0
  } catch { return 0 }      // storage refused (a private window, blocked site data): the clock starts at 0 on each page
}

export function writePlayed(seconds: number) {
  try { localStorage.setItem(PLAYED_KEY, String(Math.round(seconds))) } catch { /* as readPlayed: kept for this page only */ }
}

/** The origin a break's page answers from (a path is on this server), or null for a link that cannot be parsed: the server refuses
 *  those, but a frame that throws would also lose its time limit, so nothing answers it and the limit ends the break. */
export function pageOrigin(url: string, base = document.baseURI): string | null {
  try { return new URL(url, base).origin } catch { return null }
}

/** Whether `e` is the break's page saying it is done: from that frame, from the page's origin, with the done message. */
export function isDone(e: MessageEvent, frame: Window | null | undefined, origin: string | null): boolean {
  const data: unknown = e.data
  return !!frame && origin !== null && e.source === frame && e.origin === origin && typeof data === 'object' && data !== null && (data as { type?: unknown }).type === DONE
}

/** Counts seconds of playing: a step from one place to the next counts if it is forward and no longer than MAX_STEP. */
export class PlayClock {
  private last: number | null = null
  constructor(public played: number) {}

  /** The playhead is at `t` while playing. */
  advance(t: number) {
    if (this.last !== null && t >= this.last && t - this.last <= MAX_STEP) this.played += t - this.last
    this.last = t
  }

  /** The playhead jumped, or playing stopped: the next step starts at `t`. */
  jump(t: number) {
    this.last = t
  }
}

/** The break for the video in `ref`: whether one is up, and `end` to finish it (the clock starts again and the video plays on). */
export function useBreak(ref: RefObject<HTMLVideoElement | null>, b: Break | undefined): { due: boolean; end: () => void } {
  const [due, setDue] = useState(false)
  const dueRef = useRef(false)
  const clock = useRef<PlayClock | null>(null)
  const url = b?.url, seconds = (b?.minutes ?? 0) * 60
  useEffect(() => {
    if (!url || !seconds) return
    const video = ref.current!
    const c = (clock.current = new PlayClock(readPlayed()))
    c.jump(video.currentTime)
    let kept = Math.round(c.played)
    const keep = () => { if (Math.round(c.played) !== kept) writePlayed((kept = Math.round(c.played))) }
    const onTime = () => {
      if (dueRef.current) return
      if (video.paused || video.seeking) return c.jump(video.currentTime)
      c.advance(video.currentTime)
      keep()
      if (c.played >= seconds) { dueRef.current = true; setDue(true); video.pause() }
    }
    const onJump = () => c.jump(video.currentTime)
    const onPlay = () => { if (dueRef.current) video.pause() }      // the controls or a key cannot play through a break
    video.addEventListener('timeupdate', onTime)
    video.addEventListener('seeking', onJump)
    video.addEventListener('pause', onJump)
    video.addEventListener('play', onPlay)
    return () => {
      video.removeEventListener('timeupdate', onTime)
      video.removeEventListener('seeking', onJump)
      video.removeEventListener('pause', onJump)
      video.removeEventListener('play', onPlay)
      keep()
    }
  }, [ref, url, seconds])
  const end = useCallback(() => {
    dueRef.current = false
    setDue(false)
    clock.current!.played = 0                        // a break is only due once the clock runs
    writePlayed(0)
    void ref.current!.play().catch(() => undefined)   // a browser that refuses leaves the video paused, with its play button
  }, [ref])
  return { due, end }
}

/** The break's page, filling the picture, until it says it is done or `limitMinutes` pass. */
export function BreakFrame({ url, limitMinutes, onDone }: { url: string; limitMinutes: number; onDone: () => void }) {
  const frame = useRef<HTMLIFrameElement>(null)
  useEffect(() => {
    const timer = setTimeout(onDone, limitMinutes * 60_000)     // first: nothing below can stop the break ending
    const origin = pageOrigin(url)
    const onMessage = (e: MessageEvent) => { if (isDone(e, frame.current?.contentWindow, origin)) onDone() }
    window.addEventListener('message', onMessage)
    return () => { window.removeEventListener('message', onMessage); clearTimeout(timer) }
  }, [url, limitMinutes, onDone])
  return <iframe ref={frame} src={url} title="Break" allow="autoplay; fullscreen" className="absolute inset-0 size-full border-0 bg-tube-screen" />
}
