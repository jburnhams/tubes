import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { BreakFrame, DONE, PLAYED_KEY } from '../../src/watch/break'
import { act, openApp, screen, waitFor } from '../utils/render'
import { saveSettingsFails } from '../../src/mocks/handlers'
import { mock, server } from '../utils/server'

const id = 'wo000000000'

// jsdom's <video> neither loads nor plays: it is played to a time as Chrome would report it, and its play() and pause() are watched.
describe('Breaks', () => {
  let pause: ReturnType<typeof vi.spyOn>, play: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    localStorage.clear()
    pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    mock.settings = { ...mock.settings, break_on: 'true', break_url: '/games/play?embed=1', break_minutes: 1, break_limit_minutes: 5 }
  })
  afterEach(() => { vi.restoreAllMocks() })

  const video = () => screen.getByLabelText('Building a bird box, video', { selector: 'video' }) as HTMLVideoElement
  const set = (name: string, value: unknown) => Object.defineProperty(video(), name, { configurable: true, writable: true, value })
  const at = (t: number, paused = false) => act(() => { set('paused', paused); set('currentTime', t); video().dispatchEvent(new Event('timeupdate')) })
  const playFor = (from: number, to: number) => { for (let t = from; t <= to; t++) at(t) }
  const ready = async () => { await screen.findByRole('group', { name: 'Building a bird box' }); await waitFor(() => expect(mock.breakReads).toBeGreaterThan(0)) }
  const frame = () => screen.queryByTitle('Break') as HTMLIFrameElement | null
  const done = (origin = location.origin, source: MessageEventSource | null | undefined = frame()!.contentWindow) =>
    act(() => { window.dispatchEvent(new MessageEvent('message', { data: { type: DONE }, origin, source })) })

  it('pauses after the minutes of playing and shows the page until it says it is done', async () => {
    openApp(`/watch/${id}`)
    await ready()
    playFor(0, 59)
    expect(frame()).toBeNull()
    expect(localStorage.getItem(PLAYED_KEY)).toBe('59')
    at(60)
    expect(frame()).toHaveAttribute('src', '/games/play?embed=1')
    expect(pause).toHaveBeenCalled()
    pause.mockClear()
    act(() => { video().dispatchEvent(new Event('play')) })       // the controls or a key cannot play through it
    expect(pause).toHaveBeenCalledTimes(1)
    at(61)                                                         // nor does a late time update count
    done('http://elsewhere.example')                               // another origin is not the page
    expect(frame()).not.toBeNull()
    play.mockRejectedValueOnce(new DOMException('Autoplay refused', 'NotAllowedError'))   // left paused, with its play button
    done()
    expect(frame()).toBeNull()
    expect(play).toHaveBeenCalled()
    expect(localStorage.getItem(PLAYED_KEY)).toBe('0')
    pause.mockClear()
    act(() => { video().dispatchEvent(new Event('play')) })       // after it, playing is left alone
    expect(pause).not.toHaveBeenCalled()
  })

  it('counts only playing, carried over from earlier videos', async () => {
    localStorage.setItem(PLAYED_KEY, '50')
    openApp(`/watch/${id}`)
    await ready()
    at(0)
    at(1, true); at(9, true)                                        // paused: nothing counts
    act(() => { set('currentTime', 300); video().dispatchEvent(new Event('seeking')) })
    playFor(300, 309)                                            // 50 + 9 seconds
    expect(frame()).toBeNull()
    at(310)
    expect(frame()).not.toBeNull()
  })

  it('comes at once on Break now, and the count starts again after it', async () => {
    localStorage.setItem(PLAYED_KEY, '30')
    const { user } = openApp(`/watch/${id}`)
    await ready()
    await user.click(await screen.findByRole('button', { name: 'Break now' }))
    expect(frame()).toHaveAttribute('src', '/games/play?embed=1')
    expect(pause).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Break now' })).not.toBeInTheDocument()
    done()
    expect(frame()).toBeNull()
    expect(localStorage.getItem(PLAYED_KEY)).toBe('0')
    expect(screen.getByRole('button', { name: 'Break now' })).toBeInTheDocument()
  })

  it('never comes while breaks are off', async () => {
    mock.settings = { ...mock.settings, break_on: 'false' }
    openApp(`/watch/${id}`)
    await ready()
    playFor(0, 120)
    expect(frame()).toBeNull()
    expect(localStorage.getItem(PLAYED_KEY)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Break now' })).not.toBeInTheDocument()
  })

  it('says how a page ends a break, and saves the settings', async () => {
    mock.settings = { ...mock.settings, break_on: 'false', break_url: '', break_minutes: 20, break_limit_minutes: 10 }
    const { user } = openApp('/admin/settings?tab=breaks')
    const url = await screen.findByRole('textbox', { name: 'Page to show' })
    expect(screen.getByText(/ends the break by sending/)).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /Take breaks/ }))
    await user.click(screen.getByRole('button', { name: 'Save breaks' }))
    expect(await screen.findByText('Enter the page to show, or turn breaks off.')).toBeInTheDocument()
    await user.type(url, '/games/play')
    const minutes = screen.getByRole('textbox', { name: 'Minutes of playing between breaks' })
    await user.clear(minutes); await user.type(minutes, '15')
    const limit = screen.getByRole('textbox', { name: 'Longest break (minutes)' })
    await user.clear(limit); await user.type(limit, '3')
    await user.click(screen.getByRole('button', { name: 'Save breaks' }))
    expect(await screen.findByText('Saved', { selector: '[role=status]' })).toBeInTheDocument()
    expect(mock.settings).toMatchObject({ break_on: 'true', break_url: '/games/play', break_minutes: 15, break_limit_minutes: 3 })
  })

  it('says when the breaks could not be saved', async () => {
    server.use(saveSettingsFails)
    const { user } = openApp('/admin/settings?tab=breaks')
    await user.click(await screen.findByRole('checkbox', { name: /Take breaks/ }))     // off: the page is kept, and not needed
    await user.click(screen.getByRole('button', { name: 'Save breaks' }))
    expect((await screen.findAllByText(/The breaks were not changed\./)).length).toBeGreaterThan(0)
  })
})

describe('A break page that never says it is done', () => {
  afterEach(() => { vi.useRealTimers() })
  it('ends at the time limit', () => {
    vi.useFakeTimers()
    const onDone = vi.fn()
    render(<BreakFrame url="https://games.example/play" limitMinutes={2} onDone={onDone} />)
    vi.advanceTimersByTime(119_000)
    expect(onDone).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1_000)
    expect(onDone).toHaveBeenCalledTimes(1)
  })
})
