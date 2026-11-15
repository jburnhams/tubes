// What this browser plays as it is, asked once per page load: the play request sends it (api.play), so the server keeps a Plex file's
// own video (4K HEVC, AV1, HDR) for a browser that decodes it and converts it to H.264 only for one that does not (src/tubes/fetcher.py,
// plex_copy). The answer comes from MediaCapabilities for Media Source playback, which is how hls.js plays a copy: `hevc` and `av1` at
// 2160p, `vp9` (profile 2, 10-bit), and `hdr` when HEVC with PQ transfer and BT.2020 decodes smoothly. H.264 every browser plays.
// Where MediaCapabilities is missing (an old browser, the test DOM), only H.264 is claimed, so nothing the browser cannot play is sent.

/** The codec strings asked about, with the name the server knows each by. */
export const PROBES: { name: string; contentType: string; hdr?: boolean }[] = [
  { name: 'hevc', contentType: 'video/mp4; codecs="hvc1.2.4.L153.B0"' },
  { name: 'av1', contentType: 'video/mp4; codecs="av01.0.12M.10"' },
  { name: 'vp9', contentType: 'video/mp4; codecs="vp09.02.51.10"' },
  { name: 'hdr', contentType: 'video/mp4; codecs="hvc1.2.4.L153.B0"', hdr: true },
]

type Capabilities = Pick<MediaCapabilities, 'decodingInfo'>

/** What these capabilities decode, `h264` always first. A probe that throws or answers unsupported is left out. */
export async function probe(caps: Capabilities | undefined): Promise<string[]> {
  if (!caps?.decodingInfo) return ['h264']
  const answers = await Promise.all(PROBES.map(async p => {
    try {
      const r = await caps.decodingInfo({
        type: 'media-source',
        video: { contentType: p.contentType, width: 3840, height: 2160, bitrate: 20_000_000, framerate: 24, ...(p.hdr ? { transferFunction: 'pq', colorGamut: 'rec2020' } : {}) },
      })
      return r.supported && (!p.hdr || r.smooth) ? p.name : null
    } catch { return null }
  }))
  return ['h264', ...answers.filter((n): n is string => n !== null)]
}

let asked: Promise<string[]> | undefined

/** What this browser decodes, asked the first time and kept for the page's life. */
export function decodes(): Promise<string[]> {
  asked ??= probe(globalThis.navigator?.mediaCapabilities)
  return asked
}
