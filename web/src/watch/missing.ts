// Videos the watching side finds missing. A thumbnail that fails to load, or comes back as YouTube's
// 120×90 grey placeholder (what i.ytimg.com serves for a removed video), or a fetch that fails, is
// reported to the server (POST /api/videos/check), which asks YouTube and hides the video for good if
// it is gone. Nothing is hidden on the page's guess alone: a thumbnail can fail because the network
// did. Reports are gathered for a moment and sent together (YouTube takes 50 ids a call, one quota
// unit), each video at most once per visit. The ids the server hid are kept here so every list on the
// page drops them at once, without reloading pages already scrolled through.
import { useSyncExternalStore } from 'react'
import { api } from '../api'

/** How long reports are gathered before they are sent together. */
export const REPORT_DELAY_MS = 1500
const BATCH = 50

let reported = new Set<string>()
let queue: string[] = []
let timer: ReturnType<typeof setTimeout> | undefined
let hidden: ReadonlySet<string> = new Set<string>()
const listeners = new Set<() => void>()

/** Say this video looks missing; the server decides. */
export function reportMissing(id: string) {
  if (reported.has(id)) return
  reported.add(id); queue.push(id)
  timer ??= setTimeout(() => void flush(), REPORT_DELAY_MS)
}

/** Send what has been gathered now (the timer does this; tests call it to skip the wait). */
export async function flush() {
  timer = undefined
  while (queue.length) {
    const ids = queue.splice(0, BATCH)
    try {
      const r = await api.check(ids)
      if (r.hidden.length) { hidden = new Set([...hidden, ...r.hidden]); listeners.forEach(l => l()) }
    } catch {
      // No YouTube key, or YouTube refused: nothing is hidden on a guess.
    }
  }
}

/** The ids the server has hidden since the page opened. */
export function useHidden(): ReadonlySet<string> {
  return useSyncExternalStore(l => { listeners.add(l); return () => void listeners.delete(l) }, () => hidden)
}

/** Whether a loaded thumbnail is YouTube's placeholder for a video it no longer has: 120×90, where the size asked for is larger. */
export function isPlaceholder(img: { naturalWidth: number; naturalHeight: number; currentSrc?: string; src: string }): boolean {
  return img.naturalWidth === 120 && img.naturalHeight === 90 && !/\/default\.jpg(\?|$)/.test(img.currentSrc || img.src)
}

/** Forget every report (between tests). */
export function resetMissing() {
  if (timer) clearTimeout(timer)
  reported = new Set(); queue = []; timer = undefined; hidden = new Set()
}
