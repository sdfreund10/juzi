import { copyFileSync } from 'node:fs'
import path from 'node:path'
import preact from '@preact/preset-vite'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

function devTabIdentity(mode: string): Plugin {
  return {
    name: 'dev-tab-identity',
    transformIndexHtml(html) {
      if (mode !== 'development') {
        return html
      }
      return html
        .replace('<title>juzi</title>', '<title>juzi - Dev</title>')
        .replace(
          'name="apple-mobile-web-app-title" content="juzi"',
          'name="apple-mobile-web-app-title" content="juzi Dev"',
        )
        .replace(
          'rel="icon" type="image/svg+xml" href="/favicon.svg"',
          'rel="icon" type="image/svg+xml" href="/favicon-dev.svg"',
        )
        .replace(
          'rel="apple-touch-icon" href="/apple-touch-icon.png"',
          'rel="apple-touch-icon" href="/apple-touch-icon-dev.png"',
        )
        .replace('src="/favicon.svg"', 'src="/favicon-dev.svg"')
    },
    writeBundle(options) {
      if (mode !== 'development') {
        return
      }
      const outDir = options.dir ?? path.resolve('dist')
      copyFileSync(
        path.join(outDir, 'site-dev.webmanifest'),
        path.join(outDir, 'site.webmanifest'),
      )
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [preact(), devTabIdentity(mode)],
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
