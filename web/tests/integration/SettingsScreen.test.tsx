import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { saveSettingsFails, settingsError, shownError, shownSet } from '../../src/mocks/handlers'
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

  it('sets which videos are shown, in minutes, and says what they leave out', async () => {
    const { user } = openApp('/admin/settings?tab=shown')
    expect(await screen.findByText('These leave no video out now.')).toBeInTheDocument()
    const shortest = screen.getByRole('textbox', { name: 'Shortest video (minutes)' })
    expect(shortest).toHaveValue('')
    await user.type(shortest, '3')
    await user.type(screen.getByRole('textbox', { name: 'Longest video (minutes)' }), '90.5')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Live streams' }), 'Leave out every stream, past ones and premieres too')
    await user.click(screen.getByRole('button', { name: 'Save filters' }))
    expect(await screen.findByText('Saved', { selector: '[role=status]' })).toBeInTheDocument()
    expect(mock.shown).toMatchObject({ min_seconds: 180, max_seconds: 5430, streams: 'all' })
    expect(await screen.findByText(/^20\svideos are left out by these now\./)).toBeInTheDocument()
  })

  it('starts Shown videos from what the server holds, and empty means no limit', async () => {
    server.use(shownSet)
    const { user } = openApp('/admin/settings?tab=shown')
    const shortest = await screen.findByRole('textbox', { name: 'Shortest video (minutes)' })
    expect(shortest).toHaveValue('3')
    expect(screen.getByRole('combobox', { name: 'Live streams' })).toHaveValue('all')
    expect(screen.getByText(/^15\svideos are left out by these now\./)).toBeInTheDocument()
    await user.clear(shortest)
    await user.click(screen.getByRole('button', { name: 'Save filters' }))
    await waitFor(() => expect(mock.shown.min_seconds).toBeNull())
  })

  it('says under the length what is wrong with it, and saves nothing', async () => {
    const { user } = openApp('/admin/settings?tab=shown')
    await user.type(await screen.findByRole('textbox', { name: 'Shortest video (minutes)' }), '10')
    const longest = screen.getByRole('textbox', { name: 'Longest video (minutes)' })
    await user.type(longest, '5')
    await user.click(screen.getByRole('button', { name: 'Save filters' }))
    expect(longest).toHaveAccessibleDescription(/Make this at least the shortest length\./)
    expect(mock.shown.min_seconds).toBeNull()
  })

  it('sets the country, languages and subtitles, and saves them with the lengths', async () => {
    const { user } = openApp('/admin/settings?tab=shown')
    const country = await screen.findByRole('textbox', { name: 'Country the server watches from' })
    await user.type(country, 'gb')
    const english = screen.getByRole('checkbox', { name: /^English/ })
    expect(english).not.toBeChecked()
    expect(screen.getByText(/^41,200\svideos$/)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Videos whose language is not known' })).toHaveAccessibleDescription(/^5,400\svideos say no language/)
    await user.click(english)
    await user.click(screen.getByRole('checkbox', { name: /^French/ }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Videos whose language is not known' }), 'Leave them out')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Subtitles' }), 'Only videos with subtitles the uploader added')
    await user.click(screen.getByRole('button', { name: 'Save filters' }))
    expect(await screen.findByText('Saved', { selector: '[role=status]' })).toBeInTheDocument()
    expect(mock.shown).toMatchObject({ region: 'GB', languages: ['en', 'fr'], unknown_language: 'hide', captions: 'only', min_seconds: null })
  })

  it('starts the country, languages and subtitles from the server, and clearing them saves no limit', async () => {
    server.use(shownSet)
    const { user } = openApp('/admin/settings?tab=shown')
    const country = await screen.findByRole('textbox', { name: 'Country the server watches from' })
    expect(country).toHaveValue('GB')
    expect(screen.getByRole('checkbox', { name: /^English/ })).toBeChecked()
    expect(screen.getByRole('combobox', { name: 'Subtitles' })).toHaveValue('only')
    await user.clear(country)
    await user.click(screen.getByRole('checkbox', { name: /^English/ }))
    await user.click(screen.getByRole('button', { name: 'Save filters' }))
    await waitFor(() => expect(mock.shown).toMatchObject({ region: null, languages: [] }))
  })

  it('says the country must be two letters, and saves nothing', async () => {
    const { user } = openApp('/admin/settings?tab=shown')
    const country = await screen.findByRole('textbox', { name: 'Country the server watches from' })
    await user.type(country, 'G1')
    await user.click(screen.getByRole('button', { name: 'Save filters' }))
    expect(country).toHaveAccessibleDescription(/Enter the country as two letters/)
    expect(mock.shown.region).toBeNull()
  })

  it('keeps a chosen language the library no longer has, so it can be cleared', async () => {
    server.use(http.get('*/api/library/shown', () => HttpResponse.json({ ...mock.shown, languages: ['ja'], language_counts: [{ code: null, videos: 7 }] })))
    openApp('/admin/settings?tab=shown')
    expect(await screen.findByRole('checkbox', { name: /^Japanese/ })).toBeChecked()
    expect(screen.getByRole('combobox', { name: 'Videos whose language is not known' })).toHaveAccessibleDescription(/^7\svideos say no language/)
  })

  it('says when no video says its language yet', async () => {
    server.use(http.get('*/api/library/shown', () => HttpResponse.json({ ...mock.shown, language_counts: [] })))
    openApp('/admin/settings?tab=shown')
    expect(await screen.findByText('No video in the library says its language yet. Syncs and rechecks fill it in.')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.getByRole('combobox', { name: 'Videos whose language is not known' })).toHaveAccessibleDescription(/^0\svideos say no language/)
  })

  it('says why the server refused the filters', async () => {
    server.use(http.put('*/api/library/shown', () => HttpResponse.json({ detail: 'A length must be a number of seconds, 0 or more.' }, { status: 400 })))
    const { user } = openApp('/admin/settings?tab=shown')
    await user.click(await screen.findByRole('button', { name: 'Save filters' }))
    expect(await screen.findByText('A length must be a number of seconds, 0 or more. The filters were not changed.')).toBeInTheDocument()
  })

  it('says the filters could not be read', async () => {
    server.use(shownError)
    openApp('/admin/settings?tab=shown')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
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
