// The app's route tree, in its own module so the app (main.tsx), the jsdom tests (renderRoutes from
// strata-react/testing) and the stories build their routers from the same objects.
//
// Two frames: the watching side (watch/Shell.tsx, the old Tubes look) at /, and the admin area
// (screens/Layout.tsx, Strata's look) under /admin. Routes are real paths, not #hashes: the server
// answers every page path with the app (src/tubes/server/app.py), so a reload or a shared link opens
// that page, and anything a person would link to (search words, sort, tab) lives in the URL.
import { Navigate, type RouteObject } from 'react-router'
import { Shell } from './watch/Shell'
import { HomeScreen } from './watch/HomeScreen'
import { SearchScreen } from './watch/SearchScreen'
import { ChannelsScreen } from './watch/ChannelsScreen'
import { ChannelScreen } from './watch/ChannelScreen'
import { WatchScreen } from './watch/WatchScreen'
import { NotFoundScreen } from './watch/NotFoundScreen'
import { Layout } from './screens/Layout'
import { CacheScreen } from './screens/CacheScreen'
import { LibraryScreen } from './screens/LibraryScreen'
import { SuggestionsScreen } from './screens/SuggestionsScreen'
import { HistoryScreen } from './screens/HistoryScreen'
import { QuotaScreen } from './screens/QuotaScreen'
import { SystemScreen } from './screens/SystemScreen'
import { SettingsScreen } from './screens/SettingsScreen'

export const routes: RouteObject[] = [
  {
    path: 'admin',
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/admin/system" replace /> },
      { path: 'library', element: <LibraryScreen /> },
      { path: 'suggestions', element: <SuggestionsScreen /> },
      { path: 'history', element: <HistoryScreen /> },
      { path: 'cache', element: <CacheScreen /> },
      { path: 'quota', element: <QuotaScreen /> },
      { path: 'system', element: <SystemScreen /> },
      { path: 'settings', element: <SettingsScreen /> },
    ],
  },
  {
    element: <Shell />,
    children: [
      { index: true, element: <HomeScreen /> },
      { path: 'search', element: <SearchScreen /> },
      { path: 'channels', element: <ChannelsScreen /> },
      { path: 'channels/:id', element: <ChannelScreen /> },
      { path: 'watch/:id', element: <WatchScreen /> },
      { path: '*', element: <NotFoundScreen /> },
    ],
  },
]
