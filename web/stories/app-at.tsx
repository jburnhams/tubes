// The whole app at one URL, for screen stories: the app's own route tree (src/routes.tsx) in a
// memory router, so a story shows the screen in its frame exactly as a person reaches it, with the
// URL state (sort, tab) it was opened with.
import { useState } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes } from '../src/routes'

export function AppAt({ route }: { route: string }) {
  const [router] = useState(() => createMemoryRouter(routes, { initialEntries: [route] }))
  return <RouterProvider router={router} />
}
