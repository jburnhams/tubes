import { describe, expect, it } from 'vitest'
import { plexParams } from '../../src/api'
import { PROBES, decodes, probe } from '../../src/decodes'
import { channels } from '../../src/mocks/fixtures'
import { sourceLine } from '../../src/screens/LibraryScreen'
import { describeFollowed, describeListing, describePlex, filterFrom, filterName } from '../../src/screens/PlexScreen'

const sections = [{ key: '1', title: 'Films', type: 'movie' as const, locations: [] }, { key: '2', title: 'TV shows', type: 'show' as const, locations: [] }]

describe('what this browser decodes', () => {
  it('claims H.264 alone without MediaCapabilities', async () => {
    expect(await probe(undefined)).toEqual(['h264'])
    expect(await decodes()).toEqual(['h264'])                                        // the test DOM has none
  })

  it('names each codec that decodes, HDR only when smooth, and leaves out one that throws', async () => {
    const asked: string[] = []
    const caps = {
      decodingInfo: async (c: MediaDecodingConfiguration) => {
        asked.push(c.video!.contentType)
        if (c.video!.contentType.startsWith('video/mp4; codecs="vp09')) throw new Error('no')
        return { supported: !c.video!.contentType.includes('av01'), smooth: true, powerEfficient: true } as MediaCapabilitiesDecodingInfo
      },
    }
    expect(await probe(caps)).toEqual(['h264', 'hevc', 'hdr'])
    expect(asked).toHaveLength(PROBES.length)
  })
})

describe('the Plex page', () => {
  it('reads its filters from the address and passes on only the ones set', () => {
    expect(filterFrom(new URLSearchParams('section=2&genre=1&rating=gb%2FU&title=kite'), sections)).toEqual({ section: '2', genre: '1', contentRating: 'gb/U', title: 'kite' })
    expect(filterFrom(new URLSearchParams('section=9'), sections).section).toBe('1')                // a library that is not there: the first
    expect(filterFrom(new URLSearchParams(), []).section).toBe('')
    expect(plexParams({ section: '1', genre: '1', title: '  ' })).toEqual({ genre: '1' })
  })

  it('names a listing after its library and filters', () => {
    const genres = [{ key: '1', title: 'Animation' }]
    expect(filterName(sections[0], { section: '1', genre: '1', contentRating: 'gb/U', title: ' kite ' }, genres)).toBe('Films: Animation, gb/U, “kite”')
    expect(filterName(sections[1], { section: '2' }, genres)).toBe('TV shows')
    expect(filterName(undefined, { section: '7' }, [])).toBe('Plex')
  })

  it('says what is there and what was followed', () => {
    expect(describePlex({ configured: true, reachable: true, version: null, sections: [sections[0]] })).toMatch(/^Plex has 1\sfilm or TV library\. Follow a show or a film below, or the whole listing as a channel\.$/)
    expect(describePlex({ configured: true, reachable: false, version: null, sections: [] })).toBe('Plex does not answer: no reason given')
    expect(describeListing({ items: [{ key: '1', type: 'movie', title: 'A', year: null, thumb: null, summary: null, content_rating: null, episodes: null, section: '1', followed: true }], total: 1, params: {} })).toMatch(/^1\stitle; 1 of the 1 shown is followed\.$/)
    expect(describeFollowed({ kind: 'channel', channel: { ...channels[0], kind: 'show' }, sync: { running: true, total: 1, done: 0, current: null, added: 0, gone: 0, errors: [], started: null, finished: null } as never })).toBe(`Following ${channels[0].title}. Its episodes are being added.`)
  })
})

it('says where a channel without a handle comes from', () => {
  expect(sourceLine({ ...channels[0], handle: null, platform: 'plex' })).toBe('Plex')
  expect(sourceLine({ ...channels[0], handle: null, platform: 'iplayer' })).toBe('BBC iPlayer')
  expect(sourceLine({ ...channels[0], handle: null, platform: 'youtube' })).toBeNull()
  expect(sourceLine({ ...channels[0], handle: '@x' })).toBe('@x')
})
