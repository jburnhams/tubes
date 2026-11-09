import { describe, expect, it } from 'vitest'
import { format } from 'strata-react'
import { library } from '../../src/mocks/fixtures'
import { libraryNeverSynced, shuffleEmpty, shuffleError } from '../../src/mocks/handlers'
import { SHUFFLE_COUNT } from '../../src/screens/BrowseScreen'
import { openApp, screen, waitFor, within } from '../utils/render'
import { server } from '../utils/server'

describe('Browse', () => {
  it('says how big and fresh the library copy is, and offers videos to watch', async () => {
    const { user, router } = openApp('/')
    expect(await screen.findByText(/^24\svideos from 4\schannels, copied from the library on/)).toHaveTextContent(format.dateTime(library.synced!).replace(/\s/g, ' '))
    const grid = await screen.findByRole('list', { name: 'Videos picked at random' })
    expect(within(grid).getAllByRole('listitem')).toHaveLength(SHUFFLE_COUNT)
    expect(within(grid).getByText('Saved')).toBeInTheDocument()
    expect(within(grid).getByText('Fetching')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Shuffle' }))
    await user.click(within(grid).getAllByRole('link')[0])
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/watch\//))
  })

  it('searches titles from the form, with the words in the URL', async () => {
    const { user, router } = openApp('/')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(router.state.location.pathname).toBe('/')
    await user.type(screen.getByRole('searchbox', { name: 'Search titles' }), '  bird  ')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(router.state.location.pathname).toBe('/search')
    expect(router.state.location.search).toBe('?q=bird')
  })

  it('before the first sync, says where to make one', async () => {
    server.use(libraryNeverSynced, shuffleEmpty)
    const { user, router } = openApp('/')
    expect(await screen.findByText(/^Nothing has been copied from the library yet/)).toBeInTheDocument()
    expect(await screen.findByText('No videos yet')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Go to System' }))
    expect(router.state.location.pathname).toBe('/system')
  })

  it('says the server could not answer', async () => {
    server.use(shuffleError)
    openApp('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
