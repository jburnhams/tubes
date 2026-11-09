// The app's route tree, in its own module so the app (main.tsx), the jsdom tests (renderRoutes from
// strata-react/testing) and the stories build their routers from the same objects: a test that
// hand-copied the tree would keep passing after the app's routes changed.
//
// Routes are real paths (/channels/UC…, /search?q=…), not #hashes: the server answers every page
// path with the app (src/tubes/server/app.py), so a reload or a shared link opens that screen, and
// anything a person would link to (search words, sort, tab) lives in the URL.
import type { RouteObject } from 'react-router'
import { Layout } from './screens/Layout'
import { BrowseScreen } from './screens/BrowseScreen'
import { SearchScreen } from './screens/SearchScreen'
import { ChannelsScreen } from './screens/ChannelsScreen'
import { ChannelScreen } from './screens/ChannelScreen'
import { WatchScreen } from './screens/WatchScreen'
import { CacheScreen } from './screens/CacheScreen'
import { SystemScreen } from './screens/SystemScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { NotFoundScreen } from './screens/NotFoundScreen'

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <BrowseScreen /> },
      { path: 'search', element: <SearchScreen /> },
      { path: 'channels', element: <ChannelsScreen /> },
      { path: 'channels/:id', element: <ChannelScreen /> },
      { path: 'watch/:id', element: <WatchScreen /> },
      { path: 'cache', element: <CacheScreen /> },
      { path: 'system', element: <SystemScreen /> },
      { path: 'settings', element: <SettingsScreen /> },
      { path: '*', element: <NotFoundScreen /> },
    ],
  },
]
