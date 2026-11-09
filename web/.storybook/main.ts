import type { StorybookConfig } from '@storybook/react-vite'

// Storybook for the app's own screens and components, set up as strata-react's is: every story runs
// inside the app's providers with the network served by MSW (the same handlers the tests use), the
// a11y addon fails a story with a violation, and the build is screenshotted by strata-visual.
const config: StorybookConfig = {
  framework: '@storybook/react-vite',
  stories: ['../stories/**/*.mdx', '../stories/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-docs', '@storybook/addon-a11y', 'msw-storybook-addon'],
  staticDirs: ['./public'],
  core: {
    disableTelemetry: true,
    // Its own Vite config, so the app build's outDir (into the Python package) and dev proxy stay out of it.
    builder: { name: '@storybook/builder-vite', options: { viteConfigPath: '.storybook/vite.config.ts' } },
  },
}

export default config
