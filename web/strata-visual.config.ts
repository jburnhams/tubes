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
import { defineVisualConfig } from 'strata-react/visual'
import { handlers, streamIn } from './src/mocks/handlers'

export default defineVisualConfig({
  storybook: 'storybook-static',
  app: {
    dir: 'dist-visual',
    handlers,
    viewports: ['wide', 'phone'],
    routes: [
      { name: 'browse', path: '/' },
      { name: 'search', path: '/search?q=the' },
      { name: 'channels', path: '/channels' },
      // A channel is shot with its one page. A long list is not screenshotted: InfiniteList asks for the next
      // page on its own as its end comes near, so which rows are in view depends on timing. Paging is tested
      // in jsdom (tests/integration/ChannelsScreen).
      { name: 'channel', path: '/channels/UCworkshop00000000000001' },
      // The waiting frame, not a playing video: what a <video> draws depends on how far it got.
      { name: 'watch', path: '/watch/wo000000000', states: { fetching: streamIn('fetching'), failed: streamIn('failed') } },
      {
        name: 'cache',
        path: '/cache',
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
      { name: 'system', path: '/system' },
      {
        name: 'settings',
        path: '/settings',
        states: {
          general: [],
          appearance: { path: '/settings?tab=appearance' },
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
