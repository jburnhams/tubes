// Videos the watching side finds missing. A thumbnail that fails to load, or comes back as YouTube's
// 120×90 grey placeholder (what i.ytimg.com serves for a removed video), or a fetch that fails, is
// reported to the server (POST /api/videos/check), which asks YouTube and hides the video for good if
// it is gone. Nothing is hidden on the page's guess alone: a thumbnail can fail because the network
// did. Reports are gathered for a moment and sent together (YouTube takes 50 ids a call, one quota
// unit), each video at most once per visit. The ids the server hid are kept here only until the
// video reads have been fetched again (`useReconcile`, in the watching frame): every list on the page
// drops them at once, and after that the server's answers decide, so a video the server later finds
// again (a recheck, a fetch that works) comes back without a reload.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useSyncExternalStore } from 'react'
import { api, keys } from '../api'

/** How long reports are gathered before they are sent together. */
export const REPORT_DELAY_MS = 1500
const BATCH = 50

let reported = new Set<string>()
let queue: string[] = []
let timer: ReturnType<typeof setTimeout> | undefined
let hidden: ReadonlySet<string> = new Set<string>()
const listeners = new Set<() => void>()
const onHide = new Set<(ids: string[]) => void>()

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
      if (r.hidden.length) { hidden = new Set([...hidden, ...r.hidden]); listeners.forEach(l => l()); onHide.forEach(l => l(r.hidden)) }
    } catch {
      // No YouTube key, or YouTube refused: nothing is hidden on a guess.
    }
  }
}

/** The ids the server has hidden since the page opened. */
export function useHidden(): ReadonlySet<string> {
  return useSyncExternalStore(l => { listeners.add(l); return () => void listeners.delete(l) }, () => hidden)
}

/** Stop hiding these ids here (and let them be reported again): the server's answers are current again. */
export function forget(ids: string[]) {
  hidden = new Set([...hidden].filter(id => !ids.includes(id)))
  for (const id of ids) reported.delete(id)
  listeners.forEach(l => l())
}

/** After the server hides videos: fetch every video read again (lists, shuffle, a video's page), which then leave them out or say
 *  they are gone, and hand the decision back to those reads. Mounted once, in the watching frame. */
export function useReconcile() {
  const queryClient = useQueryClient()
  useEffect(() => {
    const l = (ids: string[]) => void queryClient.invalidateQueries({ queryKey: keys.videos }).then(() => forget(ids))
    onHide.add(l)
    return () => void onHide.delete(l)
  }, [queryClient])
}

/** Whether a loaded thumbnail is YouTube's placeholder for a video it no longer has: 120×90, where the size asked for is larger. */
export function isPlaceholder(img: { naturalWidth: number; naturalHeight: number; currentSrc?: string; src: string }): boolean {
  return img.naturalWidth === 120 && img.naturalHeight === 90 && !/\/default\.jpg(\?|$)/.test(img.currentSrc || img.src)
}

/** Forget every report (between tests). */
export function resetMissing() {
  if (timer) clearTimeout(timer)
  reported = new Set(); queue = []; timer = undefined; hidden = new Set(); onHide.clear()
}
