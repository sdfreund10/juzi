import { copyFileSync } from 'node:fs'
import path from 'node:path'
import preact from '@preact/preset-vite'
import { sentryVitePlugin } from '@sentry/vite-plugin'
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

export default defineConfig(({ mode }) => {
  const uploadSourceMaps = process.env.SENTRY_UPLOAD === 'true'
  const uploadSettings = ['SENTRY_AUTH_TOKEN', 'SENTRY_ORG', 'SENTRY_PROJECT', 'VITE_SENTRY_RELEASE']
  if (uploadSourceMaps && !uploadSettings.every((key) => process.env[key])) {
    throw new Error('Sentry release builds require upload credentials and a release SHA')
  }

  return {
    plugins: [
      preact(),
      devTabIdentity(mode),
      ...(uploadSourceMaps
        ? [
            sentryVitePlugin({
              org: process.env.SENTRY_ORG,
              project: process.env.SENTRY_PROJECT,
              authToken: process.env.SENTRY_AUTH_TOKEN,
              release: { name: process.env.VITE_SENTRY_RELEASE },
              sourcemaps: { filesToDeleteAfterUpload: ['./dist/**/*.map'] },
              telemetry: false,
            }),
          ]
        : []),
    ],
    build: {
      // Watch builds keep local maps; release maps are uploaded and then deleted.
      sourcemap: uploadSourceMaps ? 'hidden' : mode === 'development',
    },
    server: {
      port: 5173,
      proxy: {
        '/api': { target: 'http://127.0.0.1:8000' },
      },
    },
    test: {
      environment: 'happy-dom',
      include: ['src/**/*.test.ts'],
    },
  }
})
