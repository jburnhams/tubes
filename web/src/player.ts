// Attaching an HLS stream to a <video>. The server writes each copy as HLS (fMP4 segments under a
// playlist that grows while the fetch runs, src/tubes/fetcher.py), and the only browser target is
// the latest Chrome, which plays HLS through Media Source Extensions with hls.js, not natively.
//
// Two settings matter for a copy that is still being fetched: the playlist is an EVENT playlist
// without an end until the fetch finishes, which hls.js would treat as live and start near its
// newest segment, so `startPosition: 0` starts at the beginning; and hls.js keeps reloading the
// playlist until #EXT-X-ENDLIST appears, so the video plays on as segments arrive.
//
// The hls.js class is passed in rather than imported here, so the unit tests can hand it a fake
// (jsdom has no Media Source) without a module mock.

/** The part of an hls.js instance this uses. */
export interface HlsInstance {
  loadSource(src: string): void
  attachMedia(media: HTMLMediaElement): void
  on(event: string, listener: (event: string, data: { fatal?: boolean; details?: string; type?: string }) => void): void
  destroy(): void
}

/** The part of the hls.js class this uses. */
export interface HlsClass {
  new (config: { startPosition: number; lowLatencyMode: boolean }): HlsInstance
  isSupported(): boolean
  Events: { ERROR: string }
}

/** The part of a <video> this uses. */
export type Media = Pick<HTMLMediaElement, 'canPlayType' | 'removeAttribute' | 'load'> & { src: string }

/** What to say when hls.js gives up: its error type and detail are for logs, so the sentence is ours. */
export function problemText(data: { details?: string; type?: string }): string {
  if (data.type === 'networkError') return 'The video stopped arriving from the server. Reload the page to try again.'
  if (data.type === 'mediaError') return 'This browser could not decode the video. Open it in an up-to-date Chrome.'
  return `The video could not be played (${data.details ?? 'unknown error'}).`
}

/**
 * Plays `src` in `video`: through hls.js where Media Source exists, natively where the browser plays
 * HLS itself, else `onProblem` says why not. Returns the function that detaches it again.
 */
export function attach(video: Media, src: string, Hls: HlsClass, onProblem: (sentence: string) => void): () => void {
  if (Hls.isSupported()) {
    const hls = new Hls({ startPosition: 0, lowLatencyMode: false })
    hls.on(Hls.Events.ERROR, (_event, data) => { if (data.fatal) onProblem(problemText(data)) })
    hls.loadSource(src)
    hls.attachMedia(video as HTMLMediaElement)
    return () => hls.destroy()
  }
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = src
    return () => { video.removeAttribute('src'); video.load() }
  }
  onProblem('This browser cannot play the stream. Open it in an up-to-date Chrome.')
  return () => {}
}
