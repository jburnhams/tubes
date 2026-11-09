import { afterAll, afterEach, beforeAll } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { installLayoutShims } from 'strata-react/testing'
import { resetMock, server } from './server'

// jsdom does no layout and has no ResizeObserver: Strata's shims give measuring components (tables,
// virtual lists) a box to render into. Real layout is checked by the visual suite in Chromium.
installLayoutShims()

// An endpoint without a handler fails the test, so a screen cannot quietly depend on a real server.
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => { cleanup(); server.resetHandlers(); resetMock(); document.documentElement.classList.remove('dark') })
afterAll(() => server.close())

// Node 25+ defines its own `localStorage` global, which is undefined without --localstorage-file and hides jsdom's: put a working in-memory one back so storage behaves as in a browser.
if (typeof globalThis.localStorage?.getItem !== 'function') {
  const data = new Map<string, string>()
  const storage: Storage = {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: k => data.get(k) ?? null,
    key: i => Array.from(data.keys())[i] ?? null,
    removeItem: k => { data.delete(k) },
    setItem: (k, v) => { data.set(k, String(v)) },
  }
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true, writable: true })
}
