import { describe, expect, it } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { groups, videos } from '../../src/mocks/fixtures'
import { groupsEmpty, groupsError, mock, videosNone } from '../../src/mocks/handlers'
import { flush } from '../../src/watch/missing'
import { act, openApp, screen, waitFor, within } from '../utils/render'
import { server } from '../utils/server'

const [sky, workshop, birds] = groups

describe('Groups', () => {
  it('shows every group with its picture, name and count, each a link to its page', async () => {
    const { user, router } = openApp('/groups')
    const list = await screen.findByRole('list', { name: 'Groups' })
    const links = within(list).getAllByRole('link')
    expect(links.map(l => l.textContent)).toEqual([sky, workshop, birds].map(g => `${g.name}${g.videos} videos`))
    expect(links[0].querySelector('img')).toHaveAttribute('src', sky.thumbnail!)
    expect(links[2].querySelector('img')).toBeNull()
    await user.click(links[1])
    expect(router.state.location.pathname).toBe(`/groups/${workshop.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: workshop.name })).toBeInTheDocument()
  })

  it('asks again each time it is opened, so its pictures change', async () => {
    let reads = 0
    server.use(http.get('*/api/groups', () => HttpResponse.json([{ ...sky, thumbnail: videos[reads++].thumbnail }])))
    const { router } = openApp('/groups')
    const picture = async () => (await screen.findByRole('list', { name: 'Groups' })).querySelector('img')?.getAttribute('src')
    expect(await picture()).toBe(videos[0].thumbnail)
    await router.navigate('/channels')
    await screen.findByRole('heading', { level: 1, name: 'Channels' })
    await router.navigate('/groups')
    expect(await picture()).toBe(videos[1].thumbnail)
    expect(reads).toBe(2)
  })

  it('reports a picture that cannot be loaded as a missing video', async () => {
    openApp('/groups')
    const img = (await screen.findByRole('list', { name: 'Groups' })).querySelector('img')!
    fireEvent.load(img)        // a picture that loads is not reported
    await act(flush)
    expect(mock.checks).toEqual([])
    fireEvent.error(img)
    await act(flush)
    expect(mock.checks).toEqual([[sky.thumbnail_video]])
  })

  it('says where groups come from when there are none', async () => {
    server.use(groupsEmpty)
    openApp('/groups')
    expect(await screen.findByText('No groups yet')).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(groupsError)
    openApp('/groups')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})

describe('A group', () => {
  it('shows its videos with the channel each is from, and a play from it is kept with the group', async () => {
    const { user } = openApp(`/groups/${sky.id}`)
    const grid = await screen.findByRole('list', { name: `Videos in ${sky.name}` })
    expect(screen.getByText(`${sky.videos} videos`)).toBeInTheDocument()
    expect(within(grid).getAllByRole('listitem')).toHaveLength(sky.videos)
    expect(within(grid).getAllByRole('link', { name: 'Night Sky' }).length).toBeGreaterThan(0)
    await user.click(within(grid).getAllByRole('link', { name: videos.find(v => v.title.includes('Moon'))!.title })[0])
    await waitFor(() => expect(mock.playsFrom.at(-1)).toMatchObject({ source: 'group', detail: String(sky.id) }))
  })

  it('says when every video in it is hidden', async () => {
    server.use(videosNone)
    openApp(`/groups/${sky.id}`)
    expect(await screen.findByText('Nothing to watch here just now')).toBeInTheDocument()
  })

  it('says when there is no such group', async () => {
    openApp('/groups/99')
    expect(await screen.findByRole('alert')).toHaveTextContent('There is no such group.')
  })

  it('says the server could not answer', async () => {
    server.use(http.get('*/api/groups/:id', () => new HttpResponse(null, { status: 503 })))
    openApp('/groups/1')
    expect(await screen.findByRole('alert')).toHaveTextContent('(503)')
  })
})
