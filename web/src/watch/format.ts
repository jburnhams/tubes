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

/** "12K views · 3 weeks ago", leaving out what is missing. */
export function viewsAndAge(v: { views: number | null; published: string }, now?: number): string {
  return [views(v.views), ago(v.published, now)].filter(Boolean).join(' · ')
}
