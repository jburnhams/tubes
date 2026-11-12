import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { addFails, channelsError, libraryFirstVisit, libraryNoKey, removeChannelFails, syncIn } from '../../src/mocks/handlers'
import { channels, programme, syncJobs } from '../../src/mocks/fixtures'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

const table = () => screen.findByRole('grid', { name: 'Channels in the library, by title' })
const row = (name: string) => screen.getByRole('row', { name: new RegExp(name) })
/** The filled buttons, by name (AsyncButton keeps every phase's label in its text for its width). */
const filled = (...named: string[]) => screen.getAllByRole('button').filter(b => b.className.includes('bg-primary')).map(b => named.find(name => screen.queryByRole('button', { name }) === b) ?? b.textContent)

describe('Library', () => {
  it('says what it follows, and lists each channel with its counts and state', async () => {
    openApp('/admin/library')
    expect(await screen.findByText(/^24\svideos from 3\sfollowed channels\. 1\schannel is still being read back/)).toBeInTheDocument()
    await table()
    expect(within(row('Kitchen Science')).getByText('Reading back')).toBeInTheDocument()
    expect(within(row('Kitchen Science')).getByText('214')).toBeInTheDocument()
    expect(within(row('Kitchen Science')).getByText('3 hidden')).toBeInTheDocument()                // gone from YouTube, left out of the lists
    expect(within(row('Night Sky')).queryByText(/hidden/)).not.toBeInTheDocument()
    expect(within(row('Night Sky')).getByText('Up to date')).toBeInTheDocument()
    expect(within(row('Rivers and Coasts')).getByText('Not followed')).toBeInTheDocument()
    expect(within(row('Rivers and Coasts')).getByText('Never')).toBeInTheDocument()
    expect(within(row('Workshop Notes')).getByRole('link', { name: 'Workshop Notes' })).toHaveAttribute('href', '/channels/UCworkshop00000000000001')
    expect(screen.getByRole('button', { name: 'Follow Rivers and Coasts' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync Rivers and Coasts' })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Select Rivers and Coasts' })).toBeDisabled()
  })

  it('sorts by any column, with the sort in the URL', async () => {
    const { user, router } = openApp('/admin/library')
    await table()
    const order = () => screen.getAllByRole('row').slice(1).map(r => within(r).getAllByRole('link')[0].textContent)
    await user.click(screen.getByRole('columnheader', { name: 'At source' }))
    expect(order()[0]).toBe('Rivers and Coasts')
    expect(within(row('Rivers and Coasts')).getByText('–')).toBeInTheDocument()
    await user.click(screen.getByRole('columnheader', { name: 'Here' }))
    await user.click(screen.getByRole('columnheader', { name: 'Last synced' }))
    expect(order()[0]).toBe('Rivers and Coasts')
    await user.click(screen.getByRole('columnheader', { name: 'Channel' }))
    await user.click(screen.getByRole('columnheader', { name: 'Channel' }))
    expect(order()[0]).toBe('Workshop Notes')
    expect(router.state.location.search).toMatch(/sort=title\./)
  })

  it('adds a channel by its handle and starts its sync', async () => {
    const { user } = openApp('/admin/library')
    await user.type(await screen.findByRole('textbox', { name: 'Channel or video' }), ' @paperplanes ')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('Following Paper Planes. Its videos are being fetched.')).toBeInTheDocument()
    expect(await screen.findByText(/^Starting a sync of 1\schannel\.$|^Syncing 1 of 1: Paper Planes\./)).toBeInTheDocument()
    expect(await screen.findByRole('row', { name: /Paper Planes/ })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Channel or video' })).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Sync all' })).toBeDisabled()                // one sync at a time
  })

  it('adds one video', async () => {
    const { user } = openApp('/admin/library')
    await user.type(await screen.findByRole('textbox', { name: 'Channel or video' }), 'abcdefghijk')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText(/^Added “A video added on its own” from Workshop Notes\.$/)).toBeInTheDocument()
    expect(mock.job.running).toBe(false)
  })

  it('says under the field what is wrong, in the server’s words when it refused', async () => {
    const { user } = openApp('/admin/library')
    await user.click(await screen.findByRole('button', { name: 'Add' }))
    expect(screen.getByRole('textbox', { name: 'Channel or video' })).toHaveAccessibleDescription(/Paste a channel or video link/)
    await user.type(screen.getByRole('textbox', { name: 'Channel or video' }), '@nobody')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Channel or video' })).toHaveAccessibleDescription(/YouTube has no channel @nobody\./))
    server.use(addFails)
    await user.click(screen.getByRole('button', { name: /^(Add|Try again)$/ }))
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Channel or video' })).toHaveAccessibleDescription(/503/))
  })

  it('syncs every followed channel, and reads again when the sync ends', async () => {
    const { user } = openApp('/admin/library')
    await user.click(await screen.findByRole('button', { name: 'Sync all' }))
    expect(await screen.findByText(/^Syncing 1 of 3: Kitchen Science\./)).toBeInTheDocument()
    expect(mock.job.total).toBe(3)
    mock.job = syncJobs.done                                                             // the server finishes; the page polls every 2 s
    expect(await screen.findByText(/^The last sync, of 3\schannels, added 57\snew videos\. 2\svideos gone from YouTube are now hidden\.$/, {}, { timeout: 4000 })).toBeInTheDocument()
    expect(screen.getByText('Finished')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sync all' })).toBeEnabled(), { timeout: 3000 })
  })

  it('names each channel that failed in the last sync, and why', async () => {
    server.use(syncIn('failed'))
    openApp('/admin/library')
    expect(await screen.findByText('Finished with failures')).toBeInTheDocument()
    expect(screen.getByText(/: YouTube refused the request \(403: the key has used its quota/)).toHaveTextContent(/^Kitchen Science:/)
    expect(screen.getByText(/: The sync stopped: the database/)).toHaveTextContent(/^The sync:/)
  })

  it('says how far a running sync has got, and holds the sync buttons until it ends', async () => {
    server.use(syncIn('running'))
    openApp('/admin/library')
    expect(await screen.findByText(/^Syncing 2 of 3: Night Sky\. 42\snew videos so far\.$/)).toBeInTheDocument()
    await table()
    expect(screen.getByRole('button', { name: 'Sync all' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Sync Night Sky' })).toBeDisabled()
  })

  it('syncs the chosen channels, whose action is then the one filled button', async () => {
    const { user } = openApp('/admin/library')
    await table()
    expect(filled('Sync all')).toEqual(['Sync all'])
    await user.click(screen.getByRole('checkbox', { name: 'Select Night Sky' }))
    await user.click(screen.getByRole('checkbox', { name: 'Select Workshop Notes' }))
    expect(filled('Sync all', 'Sync 2')).toEqual(['Sync 2'])
    await user.click(screen.getByRole('button', { name: 'Sync 2' }))
    expect(await screen.findByText(/^Syncing 1 of 2: Night Sky\./)).toBeInTheDocument()
    expect(filled('Sync all')).toEqual(['Sync all'])                                     // the chosen rows clear: Sync all is filled again, held while the sync runs
    expect(screen.getByRole('button', { name: 'Sync all' })).toBeDisabled()
  })

  it('syncs one channel, starts one again, and follows one', async () => {
    const { user } = openApp('/admin/library')
    await table()
    await user.click(screen.getByRole('button', { name: 'Start again Kitchen Science' }))
    expect(await screen.findByText(/^Syncing 1 of 1: Kitchen Science\./)).toBeInTheDocument()
    expect(mock.channels.find(c => c.title === 'Kitchen Science')?.videos).toBe(0)
    mock.job = syncJobs.idle
    await user.click(screen.getByRole('button', { name: 'Follow Rivers and Coasts' }))
    await waitFor(() => expect(mock.channels.find(c => c.title === 'Rivers and Coasts')?.follow).toBe(true))
    expect(mock.job.current).toBe('Rivers and Coasts')
  })

  it('says why a row’s sync did not start', async () => {
    server.use(syncIn('idle'))
    mock.job = { ...syncJobs.running }                                                   // the page reads idle; the server is busy
    const { user } = openApp('/admin/library')
    await table()
    await user.click(screen.getByRole('button', { name: 'Sync Night Sky' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A sync is already running; it says how far it has got.')
  })

  it('removes a channel with a moment to undo it', async () => {
    const { user } = openApp('/admin/library')
    await table()
    await user.click(screen.getByRole('button', { name: 'Remove Night Sky' }))
    expect(await screen.findByText(/^Removed Night Sky and its 6\svideos\.$/)).toBeInTheDocument()
    expect(screen.queryByRole('row', { name: /Night Sky/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(await screen.findByRole('row', { name: /Night Sky/ })).toBeInTheDocument()
    expect(mock.channels).toHaveLength(4)
  })

  it('puts a channel back when removing it fails', async () => {
    server.use(removeChannelFails)
    const { user } = openApp('/admin/library')
    await table()
    await user.click(screen.getByRole('button', { name: 'Remove Night Sky' }))
    await user.click(screen.getByRole('button', { name: 'Remove Workshop Notes' }))      // a second removal commits the first, which the server refuses
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(await screen.findByText(/Night Sky is back: removing it did not go through\./)).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Night Sky/ })).toBeInTheDocument()
  })

  it('without a YouTube key, says so and offers only what iPlayer can do', async () => {
    server.use(libraryNoKey)
    openApp('/admin/library')
    expect(await screen.findByText(/YOUTUBE_API_KEY in its environment/)).toBeInTheDocument()
    await table()
    expect(screen.queryByRole('button', { name: 'Sync all' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Channel or video' })).toBeInTheDocument()      // an iPlayer link needs no key
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync Night Sky' })).not.toBeInTheDocument()
  })

  it('names an iPlayer programme as one, and syncs it without a YouTube key', async () => {
    server.use(libraryNoKey, http.get('*/api/channels', () => HttpResponse.json([...channels, programme])))
    openApp('/admin/library')
    const row = await screen.findByRole('row', { name: /Harbour Lights/ })
    expect(within(row).getByText('BBC iPlayer')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Sync Harbour Lights' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove Night Sky' })).toBeInTheDocument()
  })

  it('on a first visit, says how to add a channel', async () => {
    server.use(...libraryFirstVisit)
    openApp('/admin/library')
    expect(await screen.findByText('No channels yet')).toBeInTheDocument()
    expect(screen.getByText(/^The library follows no channels yet\./)).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(channelsError)
    openApp('/admin/library')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })

  it('is in the admin rail', async () => {
    const { user, router } = openApp('/admin/system')
    await user.click(await screen.findByRole('link', { name: 'Library' }))
    expect(router.state.location.pathname).toBe('/admin/library')
  })
})
