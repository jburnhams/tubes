import { describe, expect, it } from 'vitest'
import { DONE, PlayClock, isDone, pageOrigin, readPlayed, writePlayed } from '../../src/watch/break'
import { breakProblems } from '../../src/screens/SettingsScreen'

describe('the break clock', () => {
  it('counts forward steps of playing, not jumps', () => {
    const c = new PlayClock(10)
    c.advance(0)                      // the first place only sets where counting starts
    c.advance(1.5)
    c.advance(3)
    c.advance(30)                     // a jump forward (a seek the page missed) counts nothing
    c.advance(29)                     // nor a step back
    c.jump(100)
    c.advance(101)
    expect(c.played).toBe(14)
  })

  it('starts at 0 where the browser cannot keep it', () => {
    // Node has no working localStorage without a file: reading and writing are refused, and neither throws.
    expect(() => writePlayed(30)).not.toThrow()
    expect(readPlayed()).toBe(0)
  })
})

describe('the break page', () => {
  it('answers from its own origin, a path from this server', () => {
    expect(pageOrigin('/games/play', 'http://tv.example/tubes/watch/x')).toBe('http://tv.example')
    expect(pageOrigin('https://games.example:8443/play', 'http://tv.example/')).toBe('https://games.example:8443')
    expect(pageOrigin('https://[host/play', 'http://tv.example/')).toBeNull()      // the server refuses these; the frame does not throw on one
  })

  it('is done only when its own frame says so, from its origin', () => {
    const frame = {} as Window, other = {} as Window
    const message = (data: unknown, origin = 'http://tv.example', source: Window = frame) => ({ data, origin, source }) as unknown as MessageEvent
    expect(isDone(message({ type: DONE }), frame, 'http://tv.example')).toBe(true)
    expect(isDone(message({ type: DONE }, 'http://elsewhere.example'), frame, 'http://tv.example')).toBe(false)
    expect(isDone(message({ type: DONE }, undefined, other), frame, 'http://tv.example')).toBe(false)
    expect(isDone(message({ type: 'other' }), frame, 'http://tv.example')).toBe(false)
    expect(isDone(message(DONE), frame, 'http://tv.example')).toBe(false)
    expect(isDone(message(null), frame, 'http://tv.example')).toBe(false)
    expect(isDone(message({ type: DONE }), null, 'http://tv.example')).toBe(false)
    expect(isDone(message({ type: DONE }), frame, null)).toBe(false)
  })
})

describe('the Breaks form', () => {
  const f = { on: true, url: '/games/play', minutes: '20', limit: '10' }
  it('takes a link or a path, and numbers in range', () => {
    expect(breakProblems(f)).toEqual({ url: undefined, minutes: undefined, limit: undefined })
    expect(breakProblems({ ...f, url: 'https://games.example/play?x=1' }).url).toBeUndefined()
    expect(breakProblems({ ...f, url: '' }).url).toBe('Enter the page to show, or turn breaks off.')
    expect(breakProblems({ ...f, on: false, url: '' }).url).toBeUndefined()
    for (const url of ['javascript:alert(1)', '//', '//host/x', 'https://[host/play', 'https://?embed=1', 'ftp://host/x', '/a b'])
      expect(breakProblems({ ...f, url }).url).toMatch(/^Enter a link/)
    expect(breakProblems({ ...f, minutes: '0' }).minutes).toBe('Enter the time between breaks in minutes, from 1 to 1440.')
    expect(breakProblems({ ...f, minutes: ' ' }).minutes).toBeDefined()
    expect(breakProblems({ ...f, limit: 'ten' }).limit).toBe('Enter the longest break in minutes, from 1 to 240.')
  })
})
