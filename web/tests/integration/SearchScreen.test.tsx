import { describe, expect, it } from 'vitest'
import { videos } from '../../src/mocks/fixtures'
import { videosError, videosFrom } from '../../src/mocks/handlers'
import { openApp, screen, within } from '../utils/render'
import { server } from '../utils/server'

describe('Search', () => {
  it('lists the titles with every word as rows', async () => {
    openApp('/search?q=bird%20box')
    expect(screen.getByRole('searchbox', { name: 'Search titles' })).toHaveValue('bird box')
    expect(screen.getByRole('heading', { level: 1, name: 'Search: bird box' })).toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Videos matching “bird box”' })
    const row = within(list).getByRole('link', { name: /Building a bird box/ })
    expect(row).toHaveAttribute('href', '/watch/wo000000000')
    expect(row).toHaveTextContent('Workshop Notes')
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
  })

  it('names the channel from the channel list when the video does not', async () => {
    server.use(videosFrom([{ ...videos[0], channel: null }]))
    openApp('/search?q=bird')
    expect(await screen.findByRole('link', { name: /Building a bird box/ })).toHaveTextContent('Workshop Notes')
  })

  it('says when nothing matches', async () => {
    openApp('/search?q=zebra')
    expect(await screen.findByText('No titles match')).toBeInTheDocument()
  })

  it('asks for words when there are none, and ignores an empty search', async () => {
    const { user, router } = openApp('/search')
    expect(screen.getByText('Search the titles')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(router.state.location.search).toBe('')
    await user.type(screen.getByRole('searchbox', { name: 'Search titles' }), '  moon  ')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(router.state.location.search).toBe('?q=moon')
    expect(await screen.findByRole('link', { name: /The Moon through binoculars/ })).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(videosError)
    openApp('/search?q=moon')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
