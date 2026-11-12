// The visual suite, run by strata-react's own runner (`strata-visual`, from strata-react/visual):
// Playwright Chromium screenshots, light and dark, compared with committed baselines in
// tests/visual/baselines/ by pixelmatch. Two targets:
//
// - storybook: every story of the built Storybook (each screen in each server state);
// - app: the production build served as the Python server would (history fallback), each route at
//   a wide and a phone viewport, with every request answered in Node by the same MSW handlers the
//   jsdom tests use. Route states here are the ones a story cannot reach without a click: a removal
//   with its Undo bar, the bulk bar, a field's error. None of them writes to the mock server (the
//   removal is still inside its undo window when the shot is taken), so shots cannot affect each other.
//
// `npm run test:visual` builds both and compares; `npm run test:visual:update` writes new
// baselines. Look at a diff in tests/visual/output/ before accepting it.
import type { Page } from 'playwright'
import { defineVisualConfig } from 'strata-react/visual'
import { http, HttpResponse } from 'msw'
import type { Segment } from './src/api'
import { defaultSettings, episodes, kindsFor, programme } from './src/mocks/fixtures'
import { channelsEmpty, channelsError, channelsLoading, handlers, playFails, playLoading, shuffleError, streamIn, videoLoading, videosError, videosLaterPageError, videosLaterPageLoading, videosLoading, videosNone, withProgramme } from './src/mocks/handlers'

/** Waits for the player's first frame, then holds it there: paused at 0:00. */
const firstFrame = async (page: Page) => {
  await page.locator('video').evaluate(async (v: HTMLVideoElement) => {
    if (v.readyState < 2) await new Promise(done => v.addEventListener('loadeddata', done, { once: true }))
    v.pause()
    v.currentTime = 0
    await new Promise(done => v.addEventListener('seeked', done, { once: true }))
  })
}

/** Seeks the held player to `t` seconds and waits for the frame. */
const seekTo = (page: Page, t: number) => page.locator('video').evaluate(async (v: HTMLVideoElement, to) => {
  v.currentTime = to
  await new Promise(done => v.addEventListener('seeked', done, { once: true }))
}, t)

/** Scrolls to the end of the page, where a paged list asks for its next page, waits for `then`, and scrolls back to the top: a
 *  whole-page shot taken scrolled down draws the fixed top bar and rail where the window was, half way down the picture. */
const atTheEnd = async (page: Page, then: () => Promise<unknown>) => {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await then()
  await page.evaluate(() => window.scrollTo(0, 0))
}

/** The video's skippable parts, in place of the sample ones (the test card is two seconds long). */
const partsAt = (segments: Segment[]) => http.get('*/api/videos/:id/segments', () => HttpResponse.json({ segments, categories: kindsFor(defaultSettings), error: null }))

export default defineVisualConfig({
  // "3 weeks ago" under every video is worked out from now, so the clock is frozen a little after the sample library's last sync.
  time: '2026-11-09T12:00:00Z',
  storybook: 'storybook-static',
  app: {
    dir: 'dist-visual',
    handlers,
    viewports: ['wide', 'phone'],
    routes: [
      // The watching side, in the old Tubes look. Each page in its states, at both widths: the ones a story cannot reach without a
      // click or a scroll (the folded rail, the next page arriving or failing, a part skipped) are set up here.
      {
        name: 'home',
        path: '/',
        states: {
          ready: [],
          'rail-folded': { setup: async page => { await page.getByRole('button', { name: /Fold the menu|Open the menu/ }).click() } },
          'no-videos': [videosNone],
          loading: [videosLoading, channelsLoading],
          error: { handlers: [videosError], waitFor: 'role=alert' },
          'next-page-loading': { handlers: [videosLaterPageLoading], setup: page => atTheEnd(page, () => page.getByRole('button', { name: 'Show more' }).waitFor({ state: 'detached' })) },
          'next-page-failed': { handlers: [videosLaterPageError], setup: page => atTheEnd(page, () => page.getByRole('button', { name: 'Try again' }).waitFor()) },
        },
      },
      {
        name: 'search',
        path: '/search?q=the',
        states: { results: [], 'no-match': [videosNone], loading: [videosLoading], error: { handlers: [videosError], waitFor: 'role=alert' } },
      },
      { name: 'search-empty', path: '/search' },
      {
        name: 'channels',
        path: '/channels',
        states: { ready: [], 'with-programme': withProgramme, empty: [channelsEmpty], loading: [channelsLoading], error: { handlers: [channelsError], waitFor: 'role=alert' } },
      },
      // A channel is shot with its one page: the next page is asked for on its own as the end scrolls near, so the paging states
      // below wait for it before the shot.
      {
        name: 'channel',
        path: '/channels/UCworkshop00000000000001',
        states: {
          ready: [],
          'no-videos': [videosNone],
          'videos-loading': [videosLoading],
          'next-page-failed': { handlers: [videosLaterPageError], setup: page => atTheEnd(page, () => page.getByRole('button', { name: 'Try again' }).waitFor()) },
        },
      },
      { name: 'channel-programme', path: `/channels/${programme.id}`, states: { ready: withProgramme } },
      { name: 'channel-missing', path: '/channels/UCnosuchchannel000000000', waitFor: 'role=alert' },
      // The waiting frames, and the player itself: every copy is the two-second test card (src/mocks/testcard.ts), held paused on a
      // frame so the picture, the time and the controls are the same in every run.
      {
        name: 'watch',
        path: '/watch/wo000000000',
        states: {
          playing: { setup: firstFrame },
          // Still being fetched: the player says so with the copy's progress.
          growing: { handlers: streamIn('playable'), setup: firstFrame },
          // An automatic part reached: skipped, with Undo over the picture.
          skipped: { handlers: [partsAt([{ category: 'sponsor', start: 0.5, end: 1.5, action: 'skip' }])], setup: async page => { await firstFrame(page); await seekTo(page, 0.6); await page.getByText('Skipped sponsor').waitFor(); await seekTo(page, 1.5) } },
          // The parts to skip could not be read: the video plays as it is, with Try again.
          'parts-unread': { handlers: [http.get('*/api/videos/:id/segments', () => new HttpResponse(null, { status: 503 }))], setup: async page => { await firstFrame(page); await page.getByText(/could not be read/).waitFor() } },
          fetching: streamIn('fetching'),
          failed: streamIn('failed'),
          refused: { handlers: [playFails], waitFor: 'role=alert' },
          starting: [playLoading],
          loading: [videoLoading],
          'up-next-failed': { handlers: [shuffleError], setup: async page => { await firstFrame(page); await page.getByRole('alert').waitFor() } },
        },
      },
      { name: 'watch-episode', path: `/watch/${episodes[0].id}`, states: { playing: { handlers: [...withProgramme, ...streamIn('ready')], setup: firstFrame } } },
      { name: 'watch-missing', path: '/watch/zzzzzzzzzzz', waitFor: 'role=alert' },
      { name: 'not-found', path: '/no/such/page' },
      // The admin area, in Strata's look.
      {
        name: 'admin-cache',
        path: '/admin/cache',
        states: {
          ready: [],
          removed: {
            setup: async page => {
              await page.getByRole('button', { name: 'Delete What a meteor shower is' }).click()
              await page.getByRole('button', { name: 'Undo' }).waitFor()
            },
          },
        },
      },
      { name: 'admin-history', path: '/admin/history' },
      {
        name: 'admin-suggestions',
        path: '/admin/suggestions',
        states: {
          ready: [],
          dismissed: {
            setup: async page => {
              await page.getByRole('button', { name: 'Dismiss Garden Birds' }).click()
              await page.getByRole('button', { name: 'Undo' }).waitFor()
            },
          },
        },
      },
      {
        name: 'admin-library',
        path: '/admin/library',
        states: {
          ready: [],
          chosen: {
            setup: async page => {
              await page.getByRole('checkbox', { name: 'Select Night Sky' }).click({ force: true })
              await page.getByRole('checkbox', { name: 'Select Workshop Notes' }).click({ force: true })
              await page.getByRole('button', { name: 'Sync 2' }).waitFor()
            },
          },
          invalid: {
            setup: async page => {
              await page.getByRole('button', { name: 'Add' }).click()
              await page.getByText('Paste a channel or video link').waitFor()
            },
          },
        },
      },
      { name: 'admin-quota', path: '/admin/quota' },
      { name: 'admin-system', path: '/admin/system' },
      {
        name: 'admin-settings',
        path: '/admin/settings',
        states: {
          general: [],
          appearance: { path: '/admin/settings?tab=appearance' },
          shown: { path: '/admin/settings?tab=shown' },
          'shown-invalid': {
            path: '/admin/settings?tab=shown',
            setup: async page => {
              await page.getByRole('textbox', { name: 'Shortest video (minutes)' }).fill('10')
              await page.getByRole('textbox', { name: 'Longest video (minutes)' }).fill('5')
              await page.getByRole('button', { name: 'Save filters' }).click()
              await page.getByText('Make this at least the shortest length.').waitFor()
            },
          },
          invalid: {
            setup: async page => {
              await page.getByRole('textbox', { name: 'Cache folder' }).fill('videos')
              await page.getByRole('button', { name: 'Save settings' }).click()
              await page.getByText('Use a full path from the top of the disk').waitFor()
            },
          },
        },
      },
    ],
  },
})
