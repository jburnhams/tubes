import { describe, expect, it } from 'vitest'
import { openApp, screen, waitFor, within } from '../utils/render'

describe('the watching frame', () => {
  it('marks the current page in the rail, lists every channel and moves between pages by link', async () => {
    const { user, router } = openApp('/')
    const rail = screen.getByRole('navigation', { name: 'Main' })
    expect(within(rail).getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page')
    const listed = await within(rail).findByRole('region', { name: 'Channels' })
    expect(within(listed).getAllByRole('link').map(l => l.querySelector('span:not([aria-hidden])')?.textContent)).toEqual(['Kitchen Science', 'Night Sky', 'Rivers and Coasts', 'Workshop Notes'])

    await user.click(within(rail).getByRole('link', { name: 'Channels' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Channels' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/channels')
    await user.click(screen.getByRole('link', { name: 'Tubes home' }))
    expect(router.state.location.pathname).toBe('/')
  })

  it('folds the rail to icons and opens it again', async () => {
    const { user } = openApp('/')
    const fold = screen.getByRole('button', { name: 'Fold the menu' })
    expect(fold).toHaveAttribute('aria-expanded', 'true')
    await user.click(fold)
    const rail = screen.getByRole('navigation', { name: 'Main' })
    expect(within(rail).queryByRole('region', { name: 'Channels' })).toBeNull()
    expect(within(rail).getByRole('link', { name: 'Home' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open the menu' }))
    expect(await within(rail).findByRole('region', { name: 'Channels' })).toBeInTheDocument()
  })

  it('starts folded on a phone', () => {
    const was = window.matchMedia
    window.matchMedia = ((query: string) => ({ matches: query === '(max-width: 768px)', media: query, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia
    try {
      openApp('/')
      expect(screen.getByRole('button', { name: 'Open the menu' })).toHaveAttribute('aria-expanded', 'false')
    } finally { window.matchMedia = was }
  })

  it('says when a path has no page, with the way home', async () => {
    const { user, router } = openApp('/old/bookmark')
    expect(screen.getByRole('heading', { level: 1, name: 'No such page' })).toBeInTheDocument()
    expect(screen.getByText('There is nothing at /old/bookmark')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Go home' }))
    expect(router.state.location.pathname).toBe('/')
  })

  it('renders in the dark scheme', async () => {
    openApp('/channels', { colorScheme: 'dark' })
    expect(await screen.findByRole('heading', { level: 1, name: 'Channels' })).toBeInTheDocument()
    expect(document.documentElement).toHaveClass('dark')
  })
})

describe('the admin frame', () => {
  it('opens on System from the rail, and goes back to watching', async () => {
    const { user, router } = openApp('/')
    await user.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Admin' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/admin/system'))
    const menu = screen.getByRole('navigation', { name: 'Main' })
    expect(within(menu).getByRole('link', { name: 'System' })).toHaveAttribute('aria-current', 'page')
    await user.click(within(menu).getByRole('link', { name: 'Cache' }))
    expect(router.state.location.pathname).toBe('/admin/cache')
    await user.click(within(menu).getByRole('link', { name: 'Back to watching' }))
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('link', { name: 'Tubes home' })).toBeInTheDocument()
  })
})
