import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { saveSettingsFails, settingsError } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

describe('Settings', () => {
  it('starts the form from what the server holds and saves a change', async () => {
    const { user } = openApp('/admin/settings')
    const limit = await screen.findByRole('textbox', { name: 'Cache limit (GB)' })
    expect(limit).toHaveValue('1000')
    expect(screen.getByRole('textbox', { name: 'Cache folder' })).toHaveValue('/srv/tubes/cache')
    expect(screen.getByRole('combobox', { name: 'Highest quality' })).toHaveValue('1080')
    await user.clear(limit)
    await user.type(limit, '800')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Highest quality' }), '2160p')
    await user.clear(screen.getByRole('textbox', { name: 'Keep unplayed copies for (days)' }))
    await user.type(screen.getByRole('textbox', { name: 'Keep unplayed copies for (days)' }), '0')
    await user.clear(screen.getByRole('textbox', { name: 'yt-dlp player client' }))
    await user.type(screen.getByRole('textbox', { name: 'Signed-in browser' }), ' chrome+gnomekeyring ')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('Saved', { selector: '[role=status]' })).toBeInTheDocument()
    expect(mock.settings).toMatchObject({ cache_limit_gb: 800, max_height: 2160, protect_days: 0, player_client: '', cookies_from_browser: 'chrome+gnomekeyring' })
  })

  it('says under each field what is wrong, and saves nothing', async () => {
    const { user } = openApp('/admin/settings')
    const folder = await screen.findByRole('textbox', { name: 'Cache folder' })
    const ytdlp = screen.getByRole('textbox', { name: 'yt-dlp' })
    await user.clear(folder)
    await user.type(folder, 'relative/path')
    await user.clear(ytdlp)
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(folder).toHaveAccessibleDescription(/Use a full path from the top of the disk/)
    expect(ytdlp).toHaveAccessibleDescription(/Enter the yt-dlp command/)
    expect(mock.settings.cache_dir).toBe('/srv/tubes/cache')
  })

  it('says what happened when saving fails', async () => {
    server.use(saveSettingsFails)
    const { user } = openApp('/admin/settings')
    await user.click(await screen.findByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText(/The settings were not changed\./)).toBeInTheDocument()
  })

  it('says why the server refused, in its words', async () => {
    server.use(http.put('*/api/settings', () => HttpResponse.json({ detail: '/srv/tubes/cache is not writable.' }, { status: 400 })))
    const { user } = openApp('/admin/settings')
    await user.click(await screen.findByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('/srv/tubes/cache is not writable. The settings were not changed.')).toBeInTheDocument()
  })

  it('keeps the tab in the URL, and the colour scheme choice changes the page', async () => {
    const { user, router } = openApp('/admin/settings')
    await user.click(screen.getByRole('tab', { name: 'Appearance' }))
    expect(router.state.location.search).toBe('?tab=appearance')
    await user.click(screen.getByRole('radio', { name: 'Dark' }))
    await waitFor(() => expect(document.documentElement).toHaveClass('dark'))
  })

  it('opens on a tab from a link', () => {
    openApp('/admin/settings?tab=appearance')
    expect(screen.getByRole('tab', { name: 'Appearance' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('group', { name: 'Colour scheme' })).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(settingsError)
    openApp('/admin/settings')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})

describe('Settings > Skipping', () => {
  it('has a choice for each kind of segment, starting from the server, and saves them', async () => {
    const { user } = openApp('/admin/settings?tab=skipping')
    const sponsor = await screen.findByRole('group', { name: 'Sponsor' })
    expect(within(sponsor).getByRole('radio', { name: /^Skip/ })).toBeChecked()
    const filler = screen.getByRole('group', { name: 'Filler or tangent' })
    expect(within(filler).getByRole('radio', { name: /^Off/ })).toBeChecked()
    expect(screen.getAllByRole('group')).toHaveLength(9)
    await user.click(within(screen.getByRole('group', { name: 'Intro' })).getByRole('radio', { name: /^Skip/ }))
    await user.click(within(sponsor).getByRole('radio', { name: /^Ask/ }))
    await user.click(screen.getByRole('button', { name: 'Save skipping' }))
    expect(await screen.findByText('Saved', { selector: '[role=status]' })).toBeInTheDocument()
    expect(mock.settings).toMatchObject({ skip_intro: 'auto', skip_sponsor: 'ask', skip_filler: 'off' })
  })

  it('says when saving failed', async () => {
    server.use(saveSettingsFails)
    const { user } = openApp('/admin/settings?tab=skipping')
    await user.click(await screen.findByRole('button', { name: 'Save skipping' }))
    expect((await screen.findAllByText(/Nothing was changed\./)).length).toBeGreaterThan(0)
  })

  it('says when the server names no kinds', async () => {
    server.use(http.get('*/api/skipping', () => HttpResponse.json([])))
    openApp('/admin/settings?tab=skipping')
    expect(await screen.findByText('Nothing to skip')).toBeInTheDocument()
  })
})
