/// <reference types="vitest" />
import tailwindcss from '@tailwindcss/vite'
import path from 'path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  server: {
    port: 3000,
    host: '0.0.0.0',
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    }
  },
  test: {
    globals: true,
    // Default to node, but we'll override for integration
    environment: 'node',
    setupFiles: ['./tests/utils/setup.ts'],
    css: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.d.ts', '**/node_modules/**'],
      reporter: ['text', 'lcov', 'html'],
      thresholds: {
        lines: 80,
        functions: 85,
        branches: 70,
        statements: 80,
      }
    }
  }
});
