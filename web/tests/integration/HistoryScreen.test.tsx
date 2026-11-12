import { describe, expect, it } from 'vitest'
import { followFails, historyError, historyNoKey, historyNone, historyOneAccount } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

const table = (name: string) => screen.findByRole('grid', { name })

describe('History', () => {
  it('says what was watched in the last 12 months, with the top channels and videos', async () => {
    openApp('/admin/history')
    expect(await screen.findByText(/^2,140\swatches of 1,610\svideos from 212\schannels in the last 12 months\. Most watched: Puppet Theatre, 248\stimes\.$/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Watches per month' })).toBeInTheDocument()
    const channels = await table('Channels watched most in this timeframe')
    expect(within(channels).getByRole('link', { name: 'Workshop Notes' })).toHaveAttribute('href', '/channels/UCworkshop00000000000001')
    expect(within(channels).getByText('Followed')).toBeInTheDocument()
    expect(within(channels).getByRole('link', { name: 'Puppet Theatre' })).toHaveAttribute('href', 'https://www.youtube.com/channel/UCsuggest000000000000002')
    const videos = await table('Videos watched most in this timeframe')
    expect(within(videos).getByRole('link', { name: 'The puppet who lost his hat' })).toHaveAttribute('href', 'https://www.youtube.com/watch?v=pu000000001')
    expect(within(videos).getByText('A video no longer on YouTube')).toBeInTheDocument()
  })

  it('follows a channel that is not in the library yet', async () => {
    const { user } = openApp('/admin/history')
    const channels = await table('Channels watched most in this timeframe')
    expect(within(channels).queryByRole('button', { name: 'Follow Workshop Notes' })).not.toBeInTheDocument()     // followed already
    await user.click(within(channels).getByRole('button', { name: 'Follow Puppet Theatre' }))
    expect(await screen.findByText('Following Puppet Theatre. Its videos are being fetched.')).toBeInTheDocument()
    expect(mock.followed).toEqual(['UCsuggest000000000000002'])
    await waitFor(() => expect(within(channels).queryByRole('button', { name: 'Follow Puppet Theatre' })).not.toBeInTheDocument())
    expect(within(channels).getAllByText('Followed')).toHaveLength(2)
  })

  it('says why a follow did not go through, and offers none without a key', async () => {
    server.use(followFails)
    const { user, unmount } = openApp('/admin/history')
    await user.click(within(await table('Channels watched most in this timeframe')).getByRole('button', { name: 'Follow Bike Repairs' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/quota for today/)
    unmount()
    server.use(historyNoKey)
    openApp('/admin/history')
    await table('Channels watched most in this timeframe')
    expect(screen.queryByRole('button', { name: /^Follow / })).not.toBeInTheDocument()
  })

  it('changes the timeframe and the account, with both in the URL', async () => {
    const { user, router } = openApp('/admin/history')
    const range = await screen.findByRole('combobox', { name: 'Timeframe' })
    expect(within(range).getAllByRole('option').map(o => o.textContent)).toEqual(['Last 12 months', 'Last 30 days', 'All time', '2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019'])
    await user.selectOptions(range, 'Last 30 days')
    expect(await screen.findByRole('heading', { name: 'Watches per day' })).toBeInTheDocument()
    expect(screen.getByText(/in the last 30 days\./)).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Account' }), 'work')
    await waitFor(() => expect(screen.getByText(/^32\swatches/)).toBeInTheDocument())
    expect(router.state.location.search).toBe('?range=30d&source=work')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Timeframe' }), '2019')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Timeframe' }), 'All time')
    expect(await screen.findByText(/in all the history\./)).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Timeframe' }), 'Last 12 months')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Account' }), 'Every account')
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('says when nothing was watched in a year', async () => {
    openApp('/admin/history?range=2018')
    expect(await screen.findByText('Nothing was watched in 2018.')).toBeInTheDocument()
    expect(screen.getByText('Nothing watched then')).toBeInTheDocument()
  })

  it('offers no account choice for one account', async () => {
    server.use(historyOneAccount)
    openApp('/admin/history')
    await table('Channels watched most in this timeframe')
    expect(screen.queryByRole('combobox', { name: 'Account' })).not.toBeInTheDocument()
  })

  it('says where a history comes from before there is one', async () => {
    server.use(historyNone)
    openApp('/admin/history')
    expect(await screen.findByText(/^No watch history yet\. Bring one in on the Suggestions page/)).toBeInTheDocument()
    expect(screen.getByText('No watch history yet')).toBeInTheDocument()
  })

  it('says when the history cannot be read', async () => {
    server.use(historyError)
    openApp('/admin/history')
    expect((await screen.findAllByText(/could not answer|try again/i)).length).toBeGreaterThan(0)
  })
})
