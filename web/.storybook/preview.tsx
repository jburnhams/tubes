// Every story runs the way the app runs (src/main.tsx): the same faces and stylesheet, ThemeProvider
// owning the `.dark` class (driven by the toolbar, storage off, remounted per choice so stories can
// call useColorScheme), a fresh query client per story, and the network served by MSW from the
// app's own handlers. A story puts the server into another state with
// `beforeEach: ({ msw }) => msw.use(messagesError)`; the mock server's data is reset before each.
import '@fontsource-variable/source-sans-3'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource-variable/roboto'
import '../src/styles/app.css'
import { useState } from 'react'
import type { Decorator, Preview } from '@storybook/react-vite'
import { setupWorker } from 'msw/browser'
import { mswLoader } from 'msw-storybook-addon/csf3'
import { StrataQueryProvider, ThemeProvider, createQueryClient, type ColorSchemePreference } from 'strata-react'
import { handlers, resetMock } from '../src/mocks/handlers'

const withApp: Decorator = (Story, context) => {
  const theme = (context.globals as { theme?: ColorSchemePreference }).theme ?? 'light'
  // No retry, so an error story shows its error at once rather than after the app's one retry.
  const [client] = useState(() => createQueryClient({ defaultOptions: { queries: { retry: false } } }))
  return (
    <ThemeProvider key={theme} defaultPreference={theme} storageKey={null}>
      <StrataQueryProvider client={client}>
        <Story />
      </StrataQueryProvider>
    </ThemeProvider>
  )
}

const preview: Preview = {
  decorators: [withApp],
  loaders: [
    mswLoader(async () => {
      const worker = setupWorker(...handlers)
      // Relative, so the worker is found when Storybook is served from a subpath (GitHub Pages).
      await worker.start({ serviceWorker: { url: './mockServiceWorker.js' }, onUnhandledFrame: 'bypass', quiet: true })
      return worker
    }),
  ],
  beforeEach: () => { resetMock() },
  globalTypes: {
    theme: {
      description: 'Light or dark',
      toolbar: { title: 'Theme', icon: 'mirror', items: ['light', 'dark'], dynamicTitle: true },
    },
  },
  initialGlobals: { theme: 'light' },
  parameters: {
    layout: 'fullscreen',
    controls: { expanded: true },
    a11y: { test: 'error' },
    backgrounds: { disable: true },
  },
}

export default preview
