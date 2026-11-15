// The parts of a video that can be skipped (src/tubes/segments.py: SponsorBlock's categories, iPlayer's intro and
// credits mapped onto them), turned into what strata-react's MediaPlayer draws on its seek bar and acts on (`spans`,
// `spanKinds`; strata-react issue #207). The player does the rest: an "ask" part offers Skip over the picture, an
// "auto" part is skipped (or muted) as it starts with Undo, each part is acted on once.
//
// Two rules stay here because they are Tubes' and not the player's:
// - Each kind's colour is a status tone, the nearest of the five to SponsorBlock's own colour for it (green sponsor,
//   yellow self-promotion, blue intro and credits). Strata draws spans only in its status roles; the kinds' own
//   colours wait on strata-react issue #270.
// - An automatic part is acted on whatever else plays at the time (an Ask intro around an automatic sponsor read does
//   not hold it back). The player acts on the first stretch the position is in, so an automatic part is cut out of
//   any other part it overlaps: the intro becomes the part before the sponsor read and the part after it.
import type { MediaSpanData, SpanKind, SpanTone } from 'strata-react'
import type { Segment, SegmentKind, SkipMode } from '../api'

/** Each kind's setting, by id; a kind the server did not name is off. */
export function modesOf(kinds: SegmentKind[]): Record<string, SkipMode> {
  return Object.fromEntries(kinds.map(k => [k.id, k.mode]))
}

/** The segments the player acts on and draws (those whose kind is not off), earliest first. */
export function shown(segments: Segment[], modes: Record<string, SkipMode>): Segment[] {
  return segments.filter(s => (modes[s.category] ?? 'off') !== 'off').sort((a, b) => a.start - b.start || a.end - b.end)
}

/** The status tone each SponsorBlock kind is drawn in on the seek bar; any other kind is neutral. */
export const TONES: Record<string, SpanTone> = { sponsor: 'success', selfpromo: 'warning', music_offtopic: 'warning', interaction: 'danger', intro: 'info', outro: 'info', preview: 'info' }

/** The player's kinds, from the server's: label, what reaching one does, its tone. */
export function spanKindsOf(kinds: SegmentKind[]): Record<string, SpanKind> {
  return Object.fromEntries(kinds.map(k => [k.id, { label: k.label, behaviour: k.mode, tone: TONES[k.id] ?? 'neutral' }]))
}

/** The player's spans: the segments shown, with every automatic one cut out of the other parts it overlaps (see the file's notes). */
export function spansOf(segments: Segment[], kinds: SegmentKind[]): MediaSpanData[] {
  const modes = modesOf(kinds)
  const parts = shown(segments, modes)
  const autos = parts.filter(s => modes[s.category] === 'auto')
  const span = (s: Segment, start = s.start, end = s.end): MediaSpanData => ({ kind: s.category, start, end, action: s.action })
  const out = autos.map(s => span(s))
  for (const s of parts) {
    if (modes[s.category] === 'auto') continue
    let pieces: [number, number][] = [[s.start, s.end]]
    for (const a of autos) pieces = pieces.flatMap(([from, to]): [number, number][] => (a.end <= from || a.start >= to ? [[from, to]] : [[from, a.start], [a.end, to]]).filter(([x, y]) => y > x) as [number, number][])
    out.push(...pieces.map(([from, to]) => span(s, from, to)))
  }
  return out.sort((a, b) => a.start - b.start || a.end - b.end)
}
