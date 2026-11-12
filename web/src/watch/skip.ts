// What the player does in the parts of a video that can be skipped (src/tubes/segments.py: SponsorBlock's
// categories, iPlayer's intro and credits mapped onto them), as pure functions the player and the tests share.
import type { Segment, SegmentKind, SkipMode } from '../api'

/** Each kind's setting, by id; a kind the server did not name is off. */
export function modesOf(kinds: SegmentKind[]): Record<string, SkipMode> {
  return Object.fromEntries(kinds.map(k => [k.id, k.mode]))
}

/** The segments the player acts on and draws (those whose kind is not off), earliest first. */
export function shown(segments: Segment[], modes: Record<string, SkipMode>): Segment[] {
  return segments.filter(s => (modes[s.category] ?? 'off') !== 'off').sort((a, b) => a.start - b.start || a.end - b.end)
}

/** A segment's own key, to remember it was skipped (or let play) once. */
export const segmentKey = (s: Segment) => `${s.category}@${s.start}`

/** The segment playing at `t`, if any (the one that ends last when two overlap, so one skip clears both). Its end is not inside it. */
export function at(segments: Segment[], t: number): Segment | undefined {
  return segments.filter(s => t >= s.start && t < s.end).sort((a, b) => b.end - a.end)[0]
}

/** What a segment's button says: "Skip intro", "Skip sponsor". */
export function skipText(s: Segment, kinds: SegmentKind[]): string {
  const label = kinds.find(k => k.id === s.category)?.label ?? 'segment'
  return `Skip ${label.toLowerCase()}`
}

/** What is said once a segment was skipped by itself: "Skipped sponsor", or "Muted non-music section". */
export function skippedText(s: Segment, kinds: SegmentKind[]): string {
  const label = (kinds.find(k => k.id === s.category)?.label ?? 'segment').toLowerCase()
  return s.action === 'mute' ? `Muted ${label}` : `Skipped ${label}`
}

/** Where a segment sits on a timeline of `duration` seconds, as percentages; nothing when the duration is not known. */
export function place(s: Segment, duration: number | null | undefined): { left: number; width: number } | undefined {
  if (!duration || duration <= 0) return undefined
  const left = Math.max(0, Math.min(100, (s.start / duration) * 100))
  const right = Math.max(left, Math.min(100, (s.end / duration) * 100))
  return { left, width: right - left }
}
