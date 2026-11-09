import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

// Unit tests run in node (pure logic); integration tests render the app's routes in jsdom with the
// backend served by MSW from the app's own mock handlers. Dates render in UTC, as in the visual suite.
process.env.TZ = 'UTC'

export default mergeConfig(viteConfig, defineConfig({
  test: {
    projects: [
      { extends: true, test: { name: 'unit', include: ['tests/unit/**/*.test.{ts,tsx}'], environment: 'node' } },
      { extends: true, test: { name: 'integration', include: ['tests/integration/**/*.test.{ts,tsx}'], environment: 'jsdom', setupFiles: ['tests/utils/setup.ts'] } },
    ],
    // src/mocks is the test double, not the app; it is exercised by every test and story that uses it.
    coverage: { provider: 'v8', include: ['src/**/*.{ts,tsx}'], exclude: ['src/main.tsx', 'src/mocks/**'], reporter: ['text', 'lcov'] },
  },
}))
