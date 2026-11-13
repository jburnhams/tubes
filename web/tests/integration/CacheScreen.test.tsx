import { describe, expect, it } from 'vitest'
import { cacheEmpty, cacheError, cacheNearlyFull, cacheWithStart, dropFails, evictFails, pinFails } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

describe('Cache', () => {
  it('says how full it is, and lists the copies highest score first', async () => {
    openApp('/admin/cache')
    expect(await screen.findByText(/used by 6\svideos\. Trimming starts at/)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Cache used' })).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Copies, highest score first' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(6)
    expect(rows[0]).toHaveTextContent('played in the last day')
    expect(within(table).getByText('Goes first')).toBeInTheDocument()
    expect(within(table).getAllByText('Never')).toHaveLength(1)
    expect(within(table).getByText('Fetching')).toBeInTheDocument()
    expect(within(table).getByText('Failed')).toBeInTheDocument()
    expect(within(table).getAllByRole('link')[0]).toHaveAttribute('href', `/watch/${mock.items[0].video_id}`)
  })

  it('sorts by size, plays and score, with the sort in the URL', async () => {
    const { user, router } = openApp('/admin/cache')
    const table = await screen.findByRole('table', { name: 'Copies, highest score first' })
    for (const name of ['Size', 'Plays', 'Score']) {
      await user.click(within(table).getByRole('button', { name }))
      expect(router.state.location.search).toMatch(/sort=/)
    }
    await user.click(within(table).getByRole('button', { name: 'Size' }))
    expect(within(table).getByRole('columnheader', { name: 'Size' })).toHaveAttribute('aria-sort')
  })

  it('pins and unpins a copy', async () => {
    const { user } = openApp('/admin/cache')
    const first = mock.items[0]
    await user.click(await screen.findByRole('button', { name: `Pin ${first.title}` }))
    await waitFor(() => expect(mock.items[0].pinned).toBe(true))
    await user.click(await screen.findByRole('button', { name: `Unpin ${mock.items[1].title}` }))
    await waitFor(() => expect(mock.items[1].pinned).toBe(false))
  })

  it('says when a pin did not go through', async () => {
    server.use(pinFails)
    const { user } = openApp('/admin/cache')
    await user.click(await screen.findByRole('button', { name: `Pin ${mock.items[0].title}` }))
    expect(await screen.findByText(/The pin was not changed\./)).toBeInTheDocument()
  })

  it('deletes a copy with a moment to undo it', async () => {
    const { user } = openApp('/admin/cache')
    const victim = mock.items[2]
    await user.click(await screen.findByRole('button', { name: `Delete ${victim.title}` }))
    expect(screen.queryByRole('link', { name: victim.title })).toBeNull()
    expect(screen.getByText(`Deleted the copy of “${victim.title}”.`)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(screen.getByRole('link', { name: victim.title })).toBeInTheDocument()
    expect(mock.items).toContain(victim)
  })

  it('puts a copy back when deleting it fails', async () => {
    server.use(dropFails)
    const { user } = openApp('/admin/cache')
    const victim = mock.items[2]
    await user.click(await screen.findByRole('button', { name: `Delete ${victim.title}` }))
    // A second removal commits the first, which the server refuses.
    await user.click(screen.getByRole('button', { name: `Delete ${mock.items[4].title}` }))
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(await screen.findByText(/is back: deleting it did not go through\./)).toHaveTextContent(victim.title)
    expect(screen.getByRole('link', { name: victim.title })).toBeInTheDocument()
  })

  it('trims now and says what went', async () => {
    const { user } = openApp('/admin/cache')
    await user.click(await screen.findByRole('button', { name: 'Trim now' }))
    expect(await screen.findByText(/^Freed .* from 1\svideo\.$/)).toBeInTheDocument()
    expect(mock.items.some(i => i.state === 'failed')).toBe(false)
  })

  it('says when trimming had nothing to do', async () => {
    mock.items = mock.items.filter(i => i.state !== 'failed')
    const { user } = openApp('/admin/cache')
    await user.click(await screen.findByRole('button', { name: 'Trim now' }))
    expect(await screen.findByText(/^Nothing needed to go/)).toBeInTheDocument()
  })

  it('says why trimming failed', async () => {
    server.use(evictFails)
    const { user } = openApp('/admin/cache')
    await user.click(await screen.findByRole('button', { name: 'Trim now' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /Trim now|Try again/ })).toBeInTheDocument())
  })

  it('marks a copy that holds only a prefetched start', async () => {
    server.use(cacheWithStart)
    openApp('/admin/cache')
    const table = await screen.findByRole('table', { name: 'Copies, highest score first' })
    expect(within(table).getByText('Start saved')).toBeInTheDocument()
  })

  it('says when it is over the trimming line', async () => {
    server.use(cacheNearlyFull)
    openApp('/admin/cache')
    expect(await screen.findByText(/over the trimming line/)).toBeInTheDocument()
  })

  it('says how the cache fills when it is empty', async () => {
    server.use(cacheEmpty)
    openApp('/admin/cache')
    expect(await screen.findByText(/^The cache is empty\./)).toBeInTheDocument()
    expect(screen.getByText('Nothing in the cache')).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(cacheError)
    openApp('/admin/cache')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
