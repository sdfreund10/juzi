import preact from '@preact/preset-vite'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const uploadSourceMaps = process.env.SENTRY_UPLOAD === 'true'
  const uploadSettings = ['SENTRY_AUTH_TOKEN', 'SENTRY_ORG', 'SENTRY_PROJECT', 'VITE_SENTRY_RELEASE']
  if (uploadSourceMaps && !uploadSettings.every((key) => process.env[key])) {
    throw new Error('Sentry release builds require upload credentials and a release SHA')
  }

  return {
    plugins: [
      preact(),
      ...(uploadSourceMaps ? [sentryVitePlugin({
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT,
        authToken: process.env.SENTRY_AUTH_TOKEN,
        release: { name: process.env.VITE_SENTRY_RELEASE },
        sourcemaps: { filesToDeleteAfterUpload: ['./dist/**/*.map'] },
        telemetry: false,
      })] : []),
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
