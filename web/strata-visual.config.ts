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
import { handlers, streamIn } from './src/mocks/handlers'

/** Waits for the player's first frame, then holds it there: paused at 0:00. */
const firstFrame = async (page: Page) => {
  await page.locator('video').evaluate(async (v: HTMLVideoElement) => {
    if (v.readyState < 2) await new Promise(done => v.addEventListener('loadeddata', done, { once: true }))
    v.pause()
    v.currentTime = 0
    await new Promise(done => v.addEventListener('seeked', done, { once: true }))
  })
}

export default defineVisualConfig({
  // "3 weeks ago" under every video is worked out from now, so the clock is frozen a little after the sample library's last sync.
  time: '2026-11-09T12:00:00Z',
  storybook: 'storybook-static',
  app: {
    dir: 'dist-visual',
    handlers,
    viewports: ['wide', 'phone'],
    routes: [
      // The watching side, in the old Tubes look.
      { name: 'home', path: '/' },
      { name: 'search', path: '/search?q=the' },
      { name: 'channels', path: '/channels' },
      // A channel is shot with its one page: the next page is asked for on its own as the end scrolls near, so which rows are in
      // view would depend on timing. Paging is tested in jsdom (tests/integration/ChannelScreen).
      { name: 'channel', path: '/channels/UCworkshop00000000000001' },
      // The waiting frames, and the player itself: every copy is the two-second test card (src/mocks/testcard.ts), held paused on its
      // first frame so the picture, the time and the controls are the same in every run.
      {
        name: 'watch',
        path: '/watch/wo000000000',
        states: {
          playing: { setup: firstFrame },
          fetching: streamIn('fetching'),
          failed: streamIn('failed'),
        },
      },
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
