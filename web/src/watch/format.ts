// How the watching side writes numbers and dates: the way video sites do ("12K views", "3 weeks
// ago"), which reads at a glance under a thumbnail. The admin area keeps Strata's `format`.
import { runningTime } from '../api'

export { runningTime }

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })

/** "1.2K views", "1 view"; nothing when the library has no count. */
export function views(n: number | null | undefined): string | null {
  if (n === null || n === undefined) return null
  return `${compact.format(n)} ${n === 1 ? 'view' : 'views'}`
}

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'always' })
const steps: [Intl.RelativeTimeFormatUnit, number][] = [['year', 365 * 86400], ['month', 30 * 86400], ['week', 7 * 86400], ['day', 86400], ['hour', 3600], ['minute', 60]]

/** "1 video", "1,234 videos": a channel's size. */
export const videoCount = (n: number) => (n === 1 ? '1 video' : `${n.toLocaleString('en')} videos`)

/** "3 weeks ago" from an ISO time; `now` is injectable for tests. */
export function ago(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, (now - Date.parse(iso)) / 1000)
  for (const [unit, size] of steps) if (seconds >= size) return relative.format(-Math.floor(seconds / size), unit)
  return 'just now'
}

/** "S2 E4" for an iPlayer episode in a numbered series, "Christmas Special" for one in a named one; nothing for one in no series (a soap's
 *  daily episode, a film) or for a YouTube video. */
export function episodeLabel(v: { series?: string | null; episode?: number | null }): string | null {
  if (!v.series) return null
  const n = /^Series (\d+)$/.exec(v.series)
  return n ? `S${n[1]}${v.episode ? ` E${v.episode}` : ''}` : v.series
}

const SOON = 30 * 86400

/** When an iPlayer episode leaves iPlayer, said only once it is close (as iPlayer does): "Leaves iPlayer in 5 days", "Left iPlayer" once
 *  it has (only a saved copy shows then). Nothing when it is far off or the video is not from iPlayer. */
export function leaving(expires: string | null | undefined, now = Date.now()): string | null {
  if (!expires) return null
  const seconds = (Date.parse(expires) - now) / 1000
  if (Number.isNaN(seconds) || seconds > SOON) return null
  if (seconds <= 0) return 'Left iPlayer'
  if (seconds < 86400) return 'Leaves iPlayer today'
  const days = Math.floor(seconds / 86400)
  return days < 14 ? `Leaves iPlayer in ${days} ${days === 1 ? 'day' : 'days'}` : `Leaves iPlayer in ${Math.floor(days / 7)} weeks`
}

/** The line under a video's title: "12K views · 3 weeks ago" for YouTube; "S2 E4 · 3 weeks ago · Leaves iPlayer in 5 days" for iPlayer,
 *  which has no view counts. Leaves out what is missing. */
export function viewsAndAge(v: { views: number | null; published: string; series?: string | null; episode?: number | null; expires?: string | null }, now?: number): string {
  return [episodeLabel(v), views(v.views), ago(v.published, now), leaving(v.expires, now)].filter(Boolean).join(' · ')
}

/** A channel's size in its own words: "8 episodes" for an iPlayer programme. */
export function countFor(c: { platform?: string; videos: number }): string {
  if (c.platform !== 'iplayer') return videoCount(c.videos)
  return c.videos === 1 ? '1 episode' : `${c.videos.toLocaleString('en')} episodes`
}

/** Whether an iPlayer episode can still be fetched: "Until 12 Dec 2026", or "No longer offered" (a saved copy still plays). */
export function iplayerText(v: { gone: string | null; expires?: string | null }, now = Date.now()): string {
  if (v.gone || (v.expires && Date.parse(v.expires) <= now)) return 'No longer offered; a copy saved here still plays'
  return v.expires ? `Until ${new Date(v.expires).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}` : 'Offered'
}
