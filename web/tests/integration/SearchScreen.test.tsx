import { describe, expect, it } from 'vitest'
import { videosError } from '../../src/mocks/handlers'
import { openApp, screen, within } from '../utils/render'
import { server } from '../utils/server'

describe('Search', () => {
  it('lists the titles with every word, newest first', async () => {
    openApp('/search?q=bird%20box')
    expect(screen.getByRole('searchbox', { name: 'Search titles' })).toHaveValue('bird box')
    const list = await screen.findByRole('list', { name: 'Videos matching “bird box”, newest first' })
    expect(within(list).getByRole('link', { name: /Building a bird box/ })).toHaveAttribute('href', '/watch/wo000000000')
    expect(within(list).getByText(/Workshop Notes/)).toBeInTheDocument()
    expect(await screen.findByText('That is every match.')).toBeInTheDocument()
  })

  it('says when nothing matches', async () => {
    openApp('/search?q=zebra')
    expect(await screen.findByText('No titles match')).toBeInTheDocument()
  })

  it('asks for words when there are none', async () => {
    const { user, router } = openApp('/search')
    expect(screen.getByText('Search the titles')).toBeInTheDocument()
    await user.type(screen.getByRole('searchbox', { name: 'Search titles' }), 'moon')
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
