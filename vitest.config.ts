import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(viteConfig, defineConfig({
  test: {
    projects: [
      {
        extends: true,
        test: {
          include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
          name: 'unit',
          environment: 'node',
        },
      },
      {
        extends: true,
        test: {
          include: ['tests/integration/**/*.{test,spec}.{ts,tsx}'],
          name: 'integration',
          environment: 'jsdom',
        },
      },
    ],
  },
}))
