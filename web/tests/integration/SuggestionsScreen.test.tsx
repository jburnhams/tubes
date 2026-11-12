import { describe, expect, it, vi } from 'vitest'
import { addWatchedFails, dismissFails, followFails, pasteFails, refreshQuota, relatedNotAsked, renameFails, suggestionsError, suggestionsFirstVisit, suggestionsNoKey, suggestionsRelatedOnly, suggestionsTruncated, summaryError } from '../../src/mocks/handlers'
import { act, openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

const list = (name = 'Channels to consider, best first') => screen.findByRole('list', { name })
const titles = () => within(screen.getByRole('list', { name: / first$/ })).getAllByRole('listitem').map(li => within(li).getAllByRole('link')[0].textContent)
const item = (name: string) => screen.getAllByRole('listitem').find(li => within(li).queryByRole('link', { name }))!

describe('Suggestions', () => {
  it('says how many channels are left to consider, and lists them best first', async () => {
    openApp('/admin/suggestions')
    expect(await screen.findByText(/^8\schannels from 2\shistories \(home, work\) to consider, out of 5,498\swatches\. 4 of them are pointed at by related channels \(2 never watched\), asked about last on 8 Nov 2026\. 1\schannel could not be read last time\. So far 1 dismissed\.$/)).toBeInTheDocument()
    await list()
    expect(titles()).toEqual(['Bike Repairs', 'Puppet Theatre', 'Model Railways', 'Garden Birds', 'Counting Songs', 'Old Synth Sounds', 'Lathe Turning', 'Canal Boats'])
    expect(screen.getByText(/^8\schannels, best first\.$/)).toBeInTheDocument()
    const bike = item('Bike Repairs')
    expect(within(bike).getByText(/^412\swatches · 380\svideos · last .*2026 · 2,900 on YouTube$/)).toBeInTheDocument()
    expect(within(bike).getByText('Making and mending · Hobby, Vehicle')).toBeInTheDocument()
    expect(within(bike).getByRole('link', { name: 'Bike Repairs' })).toHaveAttribute('href', 'https://www.youtube.com/channel/UCsuggest000000000000001')
    expect(within(item('Puppet Theatre')).getByText('Made for kids')).toBeInTheDocument()
    expect(within(item('Model Railways')).getByText('Some videos in the library')).toBeInTheDocument()
    expect(within(item('Garden Birds')).getByText(/^96\swatches · 90\svideos · last /)).toBeInTheDocument()       // no count from YouTube
    expect(within(bike).getByText('Pointed at by Workshop Notes and Model Railways')).toBeInTheDocument()
    expect(within(item('Garden Birds')).queryByText(/Pointed at/)).not.toBeInTheDocument()
    const lathe = item('Lathe Turning')
    expect(within(lathe).getByText(/^Never watched · 640 on YouTube$/)).toBeInTheDocument()
    expect(within(lathe).getByText('Pointed at by Workshop Notes, Bike Repairs, Model Railways and 2 more')).toBeInTheDocument()
    expect(within(lathe).queryByRole('button', { name: 'Add watched videos Lathe Turning' })).not.toBeInTheDocument()     // nothing of it was watched
    expect(within(lathe).getByRole('button', { name: 'Follow Lathe Turning' })).toBeInTheDocument()
    expect(bike).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: 'Follow Bike Repairs' })).toBeInTheDocument()
  })

  it('says when it shows only the first of many', async () => {
    server.use(suggestionsTruncated)
    openApp('/admin/suggestions')
    expect(await screen.findByText('The first 8 of 250, best first.')).toBeInTheDocument()
  })

  it('narrows the list by group, topic and audience, with each in the URL', async () => {
    const { user, router } = openApp('/admin/suggestions')
    await list()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Group' }), 'Making and mending (4)')
    await waitFor(() => expect(titles()).toEqual(['Bike Repairs', 'Model Railways', 'Garden Birds', 'Lathe Turning']))
    expect(router.state.location.search).toBe('?group=1')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Group' }), 'Not in a group (2)')
    await waitFor(() => expect(titles()).toEqual(['Old Synth Sounds', 'Canal Boats']))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Group' }), 'Every group')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Topic' }), 'Music (2)')
    await waitFor(() => expect(titles()).toEqual(['Counting Songs', 'Old Synth Sounds']))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Audience' }), 'Made for kids (2)')
    await waitFor(() => expect(titles()).toEqual(['Counting Songs']))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Audience' }), 'Not made for kids')
    await waitFor(() => expect(titles()).toEqual(['Old Synth Sounds']))
    expect(router.state.location.search).toBe('?topic=Music&kids=no')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Topic' }), 'Electronic music (1)')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Audience' }), 'Made for kids (2)')
    expect(await screen.findByText('Nothing left to consider here')).toBeInTheDocument()
  })

  it('names a group, and goes back to the made-up name when cleared', async () => {
    const { user } = openApp('/admin/suggestions?group=2')
    const field = await screen.findByRole('textbox', { name: 'Name this group' })
    expect(field).toHaveValue('')
    expect(screen.getByText(/goes by its top channels: Puppet Theatre, Counting Songs\./)).toBeInTheDocument()
    await user.type(field, 'Little ones')
    await user.click(screen.getByRole('button', { name: 'Save name' }))
    expect(await screen.findByRole('option', { name: 'Little ones (2)' })).toBeInTheDocument()
    expect(mock.groups[1]).toEqual({ id: 2, name: 'Little ones', named: true, channels: 2 })
    expect(screen.getByText('Clear it to go back to a name made from its channels.')).toBeInTheDocument()
    await user.clear(screen.getByRole('textbox', { name: 'Name this group' }))
    await user.click(screen.getByRole('button', { name: /Save/ }))
    await waitFor(() => expect(mock.groups[1].named).toBe(false))
  })

  it('says why a name was not saved', async () => {
    server.use(renameFails)
    const { user } = openApp('/admin/suggestions?group=1')
    expect(await screen.findByRole('textbox', { name: 'Name this group' })).toHaveValue('Making and mending')
    await user.click(screen.getByRole('button', { name: 'Save name' }))
    expect((await screen.findAllByText(/unavailable|try again/i)).length).toBeGreaterThan(0)
  })

  it('follows a channel, which takes it off the list', async () => {
    const { user } = openApp('/admin/suggestions')
    await list()
    await user.click(screen.getByRole('button', { name: 'Follow Bike Repairs' }))
    expect(await screen.findByText('Following Bike Repairs. Its videos are being fetched.')).toBeInTheDocument()
    await waitFor(() => expect(titles()[0]).toBe('Puppet Theatre'))
    expect(mock.followed).toEqual(['UCsuggest000000000000001'])
    await user.click(screen.getByRole('button', { name: 'Follow Puppet Theatre' }))       // the first one's sync still runs: this one is taken next
    expect(await screen.findByText(/^Following Puppet Theatre\. Its videos are fetched after the 1\schannel the running sync has first\.$/)).toBeInTheDocument()
    expect(await screen.findByText(/So far 2 followed and 1 dismissed\.$/)).toBeInTheDocument()
  })

  it('adds only the watched videos, and says how many', async () => {
    const { user } = openApp('/admin/suggestions')
    await list()
    await user.click(screen.getByRole('button', { name: 'Add watched videos Model Railways' }))
    expect(await screen.findByText(/^Added 170\svideos of Model Railways to the library \(2 were there already\)\. 2\svideos YouTube no longer has\.$/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add watched videos Garden Birds' }))
    expect(await screen.findByText(/^Added 88\svideos of Garden Birds to the library\.$/)).toBeInTheDocument()
  })

  it('is worked from the keyboard: j and k move, f follows, a adds, d dismisses', async () => {
    const { user } = openApp('/admin/suggestions')
    await list()
    expect(screen.getByLabelText('Keyboard shortcuts')).toHaveTextContent(/Follow.*Add watched videos.*Dismiss/)
    await user.keyboard('j')
    expect(item('Puppet Theatre')).toHaveAttribute('aria-current', 'true')
    await user.keyboard('k')
    expect(item('Bike Repairs')).toHaveAttribute('aria-current', 'true')
    await user.keyboard('a')
    expect(await screen.findByText(/^Added 378\svideos of Bike Repairs/)).toBeInTheDocument()
    await user.keyboard('d')
    expect(await screen.findByText('Dismissed Bike Repairs.')).toBeInTheDocument()
    expect(titles()[0]).toBe('Puppet Theatre')
    await user.keyboard('f')
    expect(await screen.findByText('Following Puppet Theatre. Its videos are being fetched.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))               // nothing is left to commit after the test
  })

  it('dismisses with Undo, then commits; the dismissed tab restores one', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const { user } = openApp('/admin/suggestions', { user: { advanceTimers: vi.advanceTimersByTime } })
      await list()
      await user.click(screen.getByRole('button', { name: 'Dismiss Garden Birds' }))
      expect(screen.queryByRole('link', { name: 'Garden Birds' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Undo' }))
      expect(screen.getByRole('link', { name: 'Garden Birds' })).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Dismiss Garden Birds' }))
      await act(async () => { vi.advanceTimersByTime(10_000) })
      await waitFor(() => expect(mock.suggestions.find(x => x.title === 'Garden Birds')!.dismissed).not.toBeNull())
      await user.click(screen.getByRole('tab', { name: 'Dismissed' }))
      await list('Dismissed channels, best first')
      await waitFor(() => expect(titles()).toEqual(['Garden Birds', 'City Walks']), { timeout: 3000 })
      expect(screen.queryByRole('button', { name: 'Follow City Walks' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Restore City Walks' }))
      expect(screen.getByText('City Walks is back on the list.')).toBeInTheDocument()
      await act(async () => { vi.advanceTimersByTime(10_000) })
      await waitFor(() => expect(mock.suggestions.find(x => x.title === 'City Walks')!.dismissed).toBeNull())
    } finally { vi.useRealTimers() }
  })

  it('says when the dismissed list is empty, and when the last one here was answered', async () => {
    mock.suggestions = mock.suggestions.map(x => ({ ...x, dismissed: null }))
    const { user } = openApp('/admin/suggestions?view=dismissed')
    expect(await screen.findByText('Nothing dismissed')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'To consider' }))
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Topic' }), 'Electronic music (1)')
    await waitFor(() => expect(titles()).toEqual(['Old Synth Sounds']))
    await user.click(screen.getByRole('button', { name: 'Dismiss Old Synth Sounds' }))
    expect(screen.getByText('That was the last one here')).toBeInTheDocument()
    await user.keyboard('d')                                                    // nothing is active: the key does nothing
    await user.click(screen.getByRole('button', { name: 'Undo' }))
  })

  it('says why following, adding or dismissing did not go through', async () => {
    server.use(followFails, addWatchedFails, dismissFails)
    const { user } = openApp('/admin/suggestions')
    await list()
    await user.click(screen.getByRole('button', { name: 'Follow Bike Repairs' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/quota for today/)
    await user.click(screen.getByRole('button', { name: 'Add watched videos Bike Repairs' }))
    expect(screen.queryByText(/^Added /)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Dismiss Bike Repairs' }))
    await user.click(screen.getByRole('button', { name: 'Dismiss Puppet Theatre' }))   // a second removal commits the first, which fails
    expect(await screen.findByRole('link', { name: 'Bike Repairs' })).toBeInTheDocument()     // back on the list
    await user.click(screen.getByRole('button', { name: 'Undo' }))
  })

  it('offers nothing that needs YouTube without a key', async () => {
    server.use(suggestionsNoKey)
    const { user } = openApp('/admin/suggestions')
    expect(await screen.findByText(/Following and adding need the server’s YouTube key/)).toBeInTheDocument()
    await list()
    expect(screen.queryByRole('button', { name: 'Follow Bike Repairs' })).not.toBeInTheDocument()
    await user.keyboard('f')
    expect(mock.followed).toEqual([])
    expect(screen.getByRole('button', { name: 'Dismiss Bike Repairs' })).toBeInTheDocument()
  })

  it('regroups, and says when YouTube could not be asked', async () => {
    const { user } = openApp('/admin/suggestions')
    await list()
    await user.click(screen.getByRole('button', { name: 'Regroup' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /Regrouped/ })).toBeInTheDocument())
    server.use(refreshQuota)
    await user.click(screen.getByRole('button', { name: /Regroup/ }))
    expect(await screen.findByText(/^Regrouped, but YouTube could not be asked about the channels: YouTube refused the request \(403: quota\)\.$/)).toBeInTheDocument()
  })

  it('orders by how many of your channels point at each, with the order in the URL', async () => {
    const { user, router } = openApp('/admin/suggestions')
    await list()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Order' }), 'Most pointed at by your channels')
    await list('Channels to consider, most pointed at first')
    await waitFor(() => expect(titles().slice(0, 4)).toEqual(['Lathe Turning', 'Bike Repairs', 'Canal Boats', 'Model Railways']))
    expect(router.state.location.search).toBe('?order=suggested')
    expect(screen.getByText(/^8\schannels, most pointed at first\.$/)).toBeInTheDocument()
    await user.keyboard('a')                                                    // the active one was never watched: nothing to add
    expect(mock.suggestions.find(x => x.title === 'Lathe Turning')!.in_library).toBe(false)
  })

  it('suggests related channels before any history is imported', async () => {
    server.use(...suggestionsRelatedOnly)
    openApp('/admin/suggestions?order=suggested')
    expect(await screen.findByText(/^2\schannels from related channels to consider\. What 19\sfollowed or most watched channels point at, asked about last on 8 Nov 2026\.$/)).toBeInTheDocument()
    await list('Channels to consider, most pointed at first')
    expect(titles()).toEqual(['Lathe Turning', 'Canal Boats'])
    expect(screen.getByRole('heading', { name: 'Bring in a watch history' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Regroup' })).not.toBeInTheDocument()
  })

  it('says when YouTube has not been asked about related channels yet', async () => {
    server.use(relatedNotAsked)
    openApp('/admin/suggestions')
    expect(await screen.findByText(/YouTube has not been asked yet which channels the 24\sfollowed or most watched channels point at; the server asks every few hours\. So far 1 dismissed\.$/)).toBeInTheDocument()
  })

  it('takes a pasted list of YouTube and iPlayer channels, and shows only those to follow', async () => {
    const { user, router } = openApp('/admin/suggestions?view=dismissed')
    const box = await screen.findByRole('textbox', { name: 'Channels and programmes' })
    await user.click(screen.getByRole('button', { name: 'Add to suggestions' }))
    expect(screen.getByText('Paste at least one link, @handle or name, one a line.')).toBeInTheDocument()
    await user.type(box, 'https://www.youtube.com/@ropemaking{enter}Harbour Lights{enter}Bike Repairs{enter}No such thing')
    mock.followed = ['UCsuggest000000000000001']
    await user.click(screen.getByRole('button', { name: 'Add to suggestions' }))
    expect(await screen.findByText(/^Added 2\ssuggestions \(1 on YouTube and 1 on iPlayer\)\. Already followed: Bike Repairs\. Not found: “No such thing” \(Neither YouTube nor iPlayer has a channel or programme by that name\)\.$/)).toBeInTheDocument()
    expect(router.state.location.search).toBe('?pasted=true')
    expect(box).toHaveValue('')
    await list('Channels to consider, latest pasted first')
    await waitFor(() => expect(titles()).toEqual(['Rope Making', 'Harbour Lights']))
    expect(screen.getByRole('combobox', { name: 'Show' })).toHaveValue('pasted')
    const harbour = item('Harbour Lights')
    expect(within(harbour).getByText('iPlayer')).toBeInTheDocument()
    expect(within(harbour).getByText(/^Pasted .*2026 · 12 on iPlayer$/)).toBeInTheDocument()
    expect(within(harbour).getByRole('link', { name: 'Harbour Lights' })).toHaveAttribute('href', 'https://www.bbc.co.uk/iplayer/episodes/b0000001')
    await user.click(within(harbour).getByRole('button', { name: 'Follow Harbour Lights' }))
    await waitFor(() => expect(mock.followed).toContain('b0000001'))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Show' }), 'Everything')
    expect(router.state.location.search).toBe('')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Show' }), 'Pasted in (1)')     // Harbour Lights is followed now
    expect(router.state.location.search).toBe('?pasted=true')
  })

  it('says when nothing new was pasted, and why a paste failed', async () => {
    const { user } = openApp('/admin/suggestions')
    await user.type(await screen.findByRole('textbox', { name: 'Channels and programmes' }), 'No such thing')
    await user.click(screen.getByRole('button', { name: 'Add to suggestions' }))
    expect(await screen.findByText(/^Nothing new to suggest\. Not found:/)).toBeInTheDocument()
    server.use(pasteFails)
    await user.click(screen.getByRole('button', { name: /^Add(ed| to suggestions)$/ }))     // it says Added for a moment after the last one
    expect((await screen.findAllByText(/unavailable|try again/i)).length).toBeGreaterThan(0)
  })

  it('follows an iPlayer programme without a YouTube key', async () => {
    server.use(suggestionsNoKey)
    const { user } = openApp('/admin/suggestions?pasted=true')
    await user.type(await screen.findByRole('textbox', { name: 'Channels and programmes' }), 'Harbour Lights')
    await user.click(screen.getByRole('button', { name: 'Add to suggestions' }))
    await waitFor(() => expect(titles()).toEqual(['Harbour Lights']))
    expect(screen.getByRole('button', { name: 'Follow Harbour Lights' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Follow Bike/ })).not.toBeInTheDocument()
  })

  it('says when every channel has been answered', async () => {
    mock.followed = mock.suggestions.filter(x => !x.dismissed).map(x => x.channel_id)
    openApp('/admin/suggestions')
    expect(await screen.findByText(/^Every channel from 2\shistories \(home, work\) has been followed or dismissed\. So far 8 followed and 1 dismissed\.$/)).toBeInTheDocument()
  })

  it('is the import form before any history, and imports one', async () => {
    server.use(suggestionsFirstVisit)
    const { user } = openApp('/admin/suggestions')
    expect(await screen.findByText(/^No watch history yet\./)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Bring in a watch history' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Regroup' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Import' }))
    expect(screen.getByText('Choose the watch-history.json or watch-history.html from a Google Takeout.')).toBeInTheDocument()
    await user.upload(screen.getByLabelText('Watch history file'), new File(['[{"title":"Watched one"},{"title":"Watched two"}]'], 'watch-history.json', { type: 'application/json' }))
    await user.click(screen.getByRole('button', { name: 'Import' }))
    expect(screen.getByText('Name the history, say after the account it came from.')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: /^Name/ }), ' phone ')
    await user.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByText(/^Imported 2\swatches as phone, from /)).toBeInTheDocument()
    expect(mock.imports).toEqual([{ source: 'phone', text: '[{"title":"Watched one"},{"title":"Watched two"}]' }])
  })

  it('says why a file was refused', async () => {
    const { user } = openApp('/admin/suggestions')
    expect(await screen.findByRole('heading', { name: 'Import another history' })).toBeInTheDocument()
    await user.upload(screen.getByLabelText('Watch history file'), new File(['hello'], 'watch-history.json', { type: 'application/json' }))
    await user.type(screen.getByRole('textbox', { name: /^Name/ }), 'x')
    await user.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByText('That is not a Google Takeout watch history (watch-history.json or watch-history.html).')).toBeInTheDocument()
  })

  it('says when the suggestions or the list cannot be read', async () => {
    server.use(summaryError)
    openApp('/admin/suggestions')
    expect((await screen.findAllByText(/unavailable|went wrong|try again/i)).length).toBeGreaterThan(0)
  })

  it('says when the list cannot be read', async () => {
    server.use(suggestionsError)
    openApp('/admin/suggestions')
    await screen.findByRole('combobox', { name: 'Group' })
    expect((await screen.findAllByText(/unavailable|went wrong|try again/i)).length).toBeGreaterThan(0)
  })
})
