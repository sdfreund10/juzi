import * as Sentry from '@sentry/browser'

export function initializeMonitoring(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return

  const apiOrigin = window.location.origin.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  Sentry.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT ?? import.meta.env.MODE,
    release: import.meta.env.VITE_SENTRY_RELEASE,
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? '1'),
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      stackFrameVariables: false,
      databaseQueryData: false,
    },
    // Keep transactions available alongside spans for performance investigation.
    traceLifecycle: 'static',
    tracePropagationTargets: [/^\/api\//, new RegExp(`^${apiOrigin}/api/`)],
    integrations: (defaults) => [
      ...defaults.filter((integration) => integration.name !== 'Breadcrumbs'),
      Sentry.browserTracingIntegration({
        shouldCreateSpanForRequest: (url) => {
          const request = new URL(url, window.location.origin)
          return request.origin === window.location.origin &&
            request.pathname.startsWith('/api/') && request.pathname !== '/api/health/'
        },
      }),
    ],
    beforeSend(event) {
      delete event.user
      delete event.request
      delete event.breadcrumbs
      return event
    },
  })
}

export function reportApiFailure(method: string, path: string, status?: number): void {
  const pathname = new URL(path, window.location.origin).pathname
  if (pathname === '/api/health/') return
  // Report a stable message rather than response text or a potentially sensitive body.
  Sentry.captureException(new Error(status ? 'API server failure' : 'API network failure'), {
    tags: { method, pathname, ...(status === undefined ? {} : { status }) },
    fingerprint: ['api-failure', method, pathname, String(status ?? 'network')],
  })
}

let sessionSpan: Sentry.Span | undefined

export function startSessionTiming(): void {
  if (sessionSpan) return
  sessionSpan = Sentry.startInactiveSpan({
    name: 'study.session_ready',
    op: 'study.session_ready',
    forceTransaction: true,
    parentSpan: null,
  })
}

export function finishSessionTiming(outcome: 'ready' | 'failed' | 'empty' | 'cancelled'): void {
  if (!sessionSpan) return
  sessionSpan.setAttribute('study.outcome', outcome)
  sessionSpan.setStatus(outcome === 'failed'
    ? { code: 2, message: 'internal_error' }
    : outcome === 'cancelled' ? { code: 2, message: 'cancelled' } : { code: 1 })
  sessionSpan.end()
  sessionSpan = undefined
}

export function withSessionTiming<T>(callback: () => T): T {
  return Sentry.withActiveSpan(sessionSpan ?? null, callback)
}
