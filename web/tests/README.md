# Web tests

Vitest 5, Testing Library, user-event, MSW, and strata-react's test helpers (`strata-react/testing`). Run from `web/`: `npm run test:unit`, `npm run test:integration`, `npm run test:coverage:gate` (unit + integration together, the number CI gates on: floors in `web/coverage-floor.json`, which only ratchet up), `npm run test:coverage:all` (the same run without the gate), `npm run test:coverage` (unit only, informational), `npm run typecheck`, `npm run build`. Screenshots are a separate suite: `npm run test:visual` (below).

## Layout

- `unit/`: node environment, no DOM. Pure functions: URL builders and field checks (`api.ts`), the watching side's views and age (`watch/format.ts`), the screens' findings, the mock server's paging, and that `index.html` inlines Strata's colour-scheme script.
- `integration/`: jsdom. One file per screen (`HomeScreen`, `SearchScreen`, `ChannelsScreen` with a channel's page, `WatchScreen`; the admin `CacheScreen`, `SystemScreen`, `SettingsScreen` at `/admin/...`) plus `App` for both frames and routing. Each test opens the app at a URL with `openApp('/admin/settings?tab=appearance')` (`utils/render.tsx`), which renders the app's own route tree (`src/routes.tsx`) through `renderRoutes` from `strata-react/testing`, with a fresh query client (retries off) and ThemeProvider (storage off).
- `utils/`: `server.ts` is the msw server over the app's mock handlers (`src/mocks/handlers.ts`: **every endpoint the app calls needs a handler there**; an unanswered request fails the test). Put the server into another state with the named handlers (`server.use(videosError)`; `mock.streams[id] = streams.failed` for a copy's state); the store resets after each test. `setup.ts` installs Strata's layout shims so tables and lists measure in jsdom. `render.tsx` provides `openApp()`.
- `visual/baselines/`: committed PNGs written by `strata-visual` (see below).

## Conventions

- Test what a user sees: query by role and accessible name, as a person would; no class-name queries, no snapshots.
- One concept per `it`, named as a sentence. Cover the happy path, loading, empty, a server error and the edge values.
- No arbitrary sleeps: `findBy*`, `waitFor`, or fake timers (`vi.useFakeTimers({ shouldAdvanceTime: true })` and `openApp(route, { user: { advanceTimers: vi.advanceTimersByTime } })` to run out the undo window).
- Never mock a module or stub `fetch`: put the server into the state with MSW.
- Copy from strata-react's `format` (the admin area) joins counts with a non-breaking space: match `/^6\svideos$/`, not a typed `"6 videos"`. The watching side writes its own (`watch/format.ts`) with ordinary spaces.
- jsdom has neither MediaSource nor native HLS, so the Watch tests see the player say so; hls.js itself is tested through `attach()` with a fake class (`unit/logic.test.ts`). A long list is paged with `installFakeIntersectionObserver().scrollToEnd()`.
- A bug found while testing: write `it.todo` or `it.fails`, comment it as a finding, and don't change app behaviour in a test-only change.

## Visual tests

`strata-visual.config.ts` names two targets: every story of the built Storybook (`stories/`, one file per screen, each state set by MSW in the story's `beforeEach`), and the production build's routes at wide and phone sizes, including states reached by a click (a removal with its Undo bar, the bulk bar, a field error). Every shot is taken light and dark. `npm run test:visual` builds both and compares; diffs land in `tests/visual/output/`, which CI uploads as `visual-diffs`. `npm run test:visual:update` rewrites the baselines: look at each diff first and say in the PR which changed and why. Stories tagged `no-visual` need a click to reach their state; `visual-wide` and `visual-phone` pick the viewport.

## Coverage floors

`coverage-floor.json` holds the floors of `npm run test:coverage:gate` (lines, statements, functions, branches). After CI is green, raise them to the new totals; never lower them. `src/mocks/` (the test double) and `src/main.tsx` are outside the measurement.

## Coverage status

| File | % Lines | Status | Notes |
|---|---|---|---|
| `src/api.ts` | 100 | done | unit/logic.test.ts and every integration test |
| `src/routes.tsx` | 100 | done | integration/App.test.tsx |
| `src/player.ts` | 100 | done | unit/logic.test.ts |
| `src/screens/Layout.tsx` | 100 | done | integration/App.test.tsx |
| `src/watch/Shell.tsx`, `NotFoundScreen.tsx` | 100 | done | integration/App.test.tsx |
| `src/watch/format.ts` | 100 | done | unit/logic.test.ts |
| `src/watch/Shown.tsx`, `cards.tsx`, `useVideos.ts` | 100 | done | Home, Search and Channels tests |
| `src/watch/missing.ts` | 100 | done | integration/Missing.test.tsx, unit/logic.test.ts |
| `src/watch/HomeScreen.tsx`, `SearchScreen.tsx` | 100 | done | integration/HomeScreen, SearchScreen |
| `src/watch/ChannelsScreen.tsx`, `ChannelScreen.tsx` | 100 | done | integration/ChannelsScreen.test.tsx |
| `src/watch/WatchScreen.tsx` | 100 | done | integration/WatchScreen.test.tsx, unit/logic.test.ts |
| `src/screens/CacheScreen.tsx` | 100 | done | integration/CacheScreen.test.tsx, unit/logic.test.ts |
| `src/screens/SystemScreen.tsx` | 100 | done | integration/SystemScreen.test.tsx, unit/logic.test.ts |
| `src/screens/HistoryScreen.tsx` | 100 | done | integration/HistoryScreen.test.tsx, unit/logic.test.ts |
| `src/screens/SuggestionsScreen.tsx` | 100 | done | integration/SuggestionsScreen.test.tsx, unit/logic.test.ts |
| `src/screens/SettingsScreen.tsx` | 100 | done | integration/SettingsScreen.test.tsx, unit/logic.test.ts |
