import { describe, expect, it } from 'vitest'
import { createQueryClient } from 'strata-react'
import { keys } from '../../src/api'
import { systemStatus } from '../../src/mocks/fixtures'
import { syncFails, systemError, systemInTrouble } from '../../src/mocks/handlers'
import { openApp, screen } from '../utils/render'
import { mock, server } from '../utils/server'

describe('System', () => {
  it('says all is ready, with the library copy, the tools and the disk', async () => {
    openApp('/admin/system')
    expect(await screen.findByText(/^Everything is ready\. The library was copied on/)).toBeInTheDocument()
    expect(screen.getByText(/^24\svideos from 4\schannels$/)).toBeInTheDocument()
    expect(screen.getByText('Set')).toBeInTheDocument()
    expect(screen.getByText('2026.10.26')).toBeInTheDocument()
    expect(screen.getByText('ffmpeg version 8.0')).toBeInTheDocument()
    expect(screen.getByText('Can fetch')).toBeInTheDocument()
    expect(screen.getByText(/^1\svideo$/)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Cache disk space used' })).toHaveAttribute('aria-valuenow', String(6_120e9))
    expect(screen.getByText('/srv/tubes/cache')).toBeInTheDocument()
    expect(screen.getAllByText('Answering')).toHaveLength(2)
  })

  it('names the first thing that is wrong, and shows each one', async () => {
    server.use(systemInTrouble)
    openApp('/admin/system')
    expect(await screen.findByText(/^This server cannot fetch videos/)).toBeInTheDocument()
    expect(screen.getByText('Missing')).toBeInTheDocument()
    expect(screen.getByText('Cannot fetch')).toBeInTheDocument()
    expect(screen.getByText('Never')).toBeInTheDocument()
    expect(screen.getByText('Not set')).toBeInTheDocument()
    expect(screen.getByText('Nothing')).toBeInTheDocument()
    expect(screen.getByText('Nearly full')).toBeInTheDocument()
  })

  it('syncs the library now', async () => {
    const { user } = openApp('/admin/system')
    await user.click(await screen.findByRole('button', { name: 'Sync now' }))
    expect(await screen.findByText('Synced', { selector: '[role=status]' })).toBeInTheDocument()
    expect(mock.synced).toBe('2026-11-09T09:30:00+00:00')
  })

  it('says why a sync was refused, in the server’s words', async () => {
    server.use(syncFails)
    const { user } = openApp('/admin/system')
    await user.click(await screen.findByRole('button', { name: 'Sync now' }))
    expect(await screen.findByText('The library cannot be read without CLOUDFLARE_API_TOKEN. The copy was not changed.')).toBeInTheDocument()
  })

  it('links to cache and settings in the app and to the API outside it', async () => {
    openApp('/admin/system')
    expect(await screen.findByRole('link', { name: /^Settings/, description: /The cache limit and folder/ })).toHaveAttribute('href', '/admin/settings')
    expect(screen.getByRole('link', { name: /^Cache/, description: /Trim now/ })).toHaveAttribute('href', '/admin/cache')
    expect(screen.getByRole('link', { name: /API reference/ })).toHaveAttribute('href', '/api/docs')
    expect(screen.getByRole('link', { name: /Health check/ })).toHaveAttribute('href', '/api/health')
  })

  it('says the server could not answer', async () => {
    server.use(systemError)
    openApp('/admin/system')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})

describe('System, when a poll fails after a good one', () => {
  it('keeps the last readings and says how old they are', async () => {
    const client = createQueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(keys.system, systemStatus, { updatedAt: Date.UTC(2026, 10, 9, 8, 50) })
    server.use(systemError)
    openApp('/admin/system', { client })
    expect(await screen.findByText(/These readings are from 08:50\./)).toBeInTheDocument()
    expect(screen.getByText('Not answering')).toBeInTheDocument()
    expect(screen.getByText(/^The server is not answering/)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Cache disk space used' })).toBeInTheDocument()
  })
})
