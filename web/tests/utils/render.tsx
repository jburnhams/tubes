// Render the app the way it runs: its own route tree (src/routes.tsx) in a memory data router, inside
// Strata's providers (renderRoutes from strata-react/testing: a fresh query client with retries
// off, ThemeProvider with storage off), with a user-event `user` beside the usual queries.
import userEvent from '@testing-library/user-event'
import { renderRoutes, type RenderRoutesOptions } from 'strata-react/testing'
import { routes } from '../../src/routes'

/** The app at `route` (`/settings?tab=appearance`). Returns `router` too, to assert where the URL went. */
export function openApp(route = '/', options: Omit<RenderRoutesOptions, 'route'> & { user?: Parameters<typeof userEvent.setup>[0] } = {}) {
  const { user: userOptions, ...rest } = options
  return { user: userEvent.setup(userOptions), ...renderRoutes(routes, { route, ...rest }) }
}

export { screen, waitFor, within, act } from '@testing-library/react'
