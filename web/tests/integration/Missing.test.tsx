import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { streams, videos } from '../../src/mocks/fixtures'
import { flush } from '../../src/watch/missing'
import { fireEvent } from '@testing-library/react'
import { act, openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

// A video the watching side finds missing is reported to the server, which asks YouTube and hides it
// if it is gone (watch/missing.ts). Reports wait REPORT_DELAY_MS to be sent together; `flush()` sends
// them at once. Thumbnails have alt="" (the title link names the video), so they are found as images
// inside each card rather than by role.
const thumbnailOf = (card: HTMLElement) => card.querySelector('img')!

async function cards() {
  const grid = await screen.findByRole('list', { name: 'Newest videos' })
  return within(grid).getAllByRole('listitem')
}

describe('Missing videos', () => {
  it('reports thumbnails that fail, together, and drops the cards the server hid', async () => {
    openApp('/')
    const [, second, third] = await cards()
    mock.gone = [videos[1].id]
    fireEvent.error(thumbnailOf(second)); fireEvent.error(thumbnailOf(third)); fireEvent.error(thumbnailOf(third))
    await act(flush)
    expect(mock.checks).toEqual([[videos[1].id, videos[2].id]])                     // one call, each video once
    await waitFor(() => expect(screen.queryByRole('link', { name: videos[1].title })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: videos[2].title })).toBeInTheDocument()  // YouTube still has it: it stays
  })

  it('shows a hidden video again once the server has it back', async () => {
    const { user } = openApp('/')
    const [, second] = await cards()
    mock.gone = [videos[1].id]; fireEvent.error(thumbnailOf(second)); await act(flush)
    await waitFor(() => expect(screen.queryByRole('link', { name: videos[1].title })).not.toBeInTheDocument())
    mock.gone = []                                                                    // a recheck, or a fetch that worked, found it again
    await user.click(screen.getByRole('link', { name: 'Channels' }))
    await user.click(screen.getByRole('link', { name: 'Home' }))
    expect(await screen.findByRole('link', { name: videos[1].title })).toBeInTheDocument()
  })

  it('reads the video again when its copy turns out whole after all', async () => {
    const id = videos[1].id
    mock.gone = [id]; mock.streams[id] = streams.fetching
    openApp(`/watch/${id}`)
    expect(await screen.findByText('No longer there (removed or made private)', { selector: 'dd' })).toBeInTheDocument()
    mock.gone = []; mock.streams[id] = streams.ready                                  // the fetch worked: the server cleared the mark
    await waitFor(() => expect(screen.queryByText('No longer there (removed or made private)', { selector: 'dd' })).not.toBeInTheDocument())
  })

  it('reports YouTube\'s grey placeholder, not a small thumbnail that was asked for', async () => {
    openApp('/')
    const [, second, third] = await cards()
    const img = (card: HTMLElement, src: string) => {
      const i = thumbnailOf(card)
      Object.defineProperties(i, { naturalWidth: { value: 120 }, naturalHeight: { value: 90 }, src: { value: src, configurable: true }, currentSrc: { value: src } })
      return i
    }
    fireEvent.load(img(second, 'https://i.ytimg.com/vi/x/hqdefault.jpg')); fireEvent.load(img(third, 'https://i.ytimg.com/vi/y/default.jpg'))
    await act(flush)
    expect(mock.checks).toEqual([[videos[1].id]])
  })

  it('hides nothing when the server cannot check', async () => {
    server.use(http.post('*/api/videos/check', () => HttpResponse.json({ detail: 'YouTube cannot be asked without YOUTUBE_API_KEY in the server’s environment.' }, { status: 503 })))
    openApp('/')
    const [, second] = await cards()
    fireEvent.error(thumbnailOf(second)); await act(flush)
    expect(screen.getByRole('link', { name: videos[1].title })).toBeInTheDocument()
  })

  it('says a failed fetch is a video YouTube no longer has', async () => {
    const id = videos[1].id
    mock.streams[id] = streams.failed
    openApp(`/watch/${id}`)
    expect(await screen.findByText('This video could not be fetched')).toBeInTheDocument()
    mock.gone = [id]                                                                  // what YouTube will say when asked
    await waitFor(() => expect(mock.checks).toEqual([]))
    await act(flush)
    expect(mock.checks).toEqual([[id]])
    expect(await screen.findByText('This video is no longer on YouTube')).toBeInTheDocument()
    expect(screen.getByText('It was removed or made private, and there is no copy on this server.')).toBeInTheDocument()
    expect(screen.getByText('No longer there (removed or made private)', { selector: 'dd' })).toBeInTheDocument()
  })

  it('says so on the page of a video the server already hid', async () => {
    const v = { ...videos[1], gone: '2026-11-01T00:00:00+00:00', plays: 0, last_played: null }
    server.use(http.get(`*/api/videos/${v.id}`, () => HttpResponse.json(v)))
    openApp(`/watch/${v.id}`)
    expect(await screen.findByText('No longer there (removed or made private)', { selector: 'dd' })).toBeInTheDocument()
  })

  it('sends reports by itself after a moment, and drops hidden rows from search results', async () => {
    openApp('/search?q=salt')
    const rows = within(await screen.findByRole('list', { name: 'Videos matching “salt”' })).getAllByRole('listitem')
    const [v] = videos.filter(x => x.title.toLowerCase().includes('salt'))
    const row = rows.find(r => within(r).queryByText(v.title))!
    mock.gone = [v.id]; fireEvent.error(thumbnailOf(row))
    await waitFor(() => expect(screen.queryByText(v.title)).not.toBeInTheDocument(), { timeout: 4000 })
    expect(mock.checks).toEqual([[v.id]])
  })
})
