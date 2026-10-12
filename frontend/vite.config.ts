import preact from '@preact/preset-vite'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [preact()],
  build: {
    // Sourcemaps for `npm run dev` (watch → frontend/dist for Django :8000).
    sourcemap: mode === 'development',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
      },
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
  },
}))
