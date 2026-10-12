import * as Sentry from '@sentry/browser'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from './api'
import { finishSessionTiming, initializeMonitoring, startSessionTiming, withSessionTiming } from './monitoring'

type Envelope = Parameters<ReturnType<NonNullable<Sentry.BrowserOptions['transport']>>['send']>[0]
const envelopes: Envelope[] = []

beforeEach(() => {
  envelopes.length = 0
  Sentry.init({
    dsn: 'https://public@example.com/1',
    traceLifecycle: 'static',
    tracesSampleRate: 1,
    defaultIntegrations: false,
    transport: () => ({
      send: async (envelope) => { envelopes.push(envelope); return {} },
      flush: async () => true,
    }),
  })
})

afterEach(async () => {
  finishSessionTiming('cancelled')
  await Sentry.close()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

function payloads(type: string) {
  return envelopes.flatMap(([, items]) => items
    .filter(([header]) => header.type === type)
    .map(([, payload]) => payload as Sentry.Event))
}

describe('API monitoring', () => {
  it('captures a server failure without submitted or response data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'private response' }), { status: 503 },
    )))
    await expect(apiRequest('/api/ratings/?secret=hidden', {
      method: 'POST', body: { password: 'private password', word: 'private study content' },
    })).rejects.toMatchObject({ status: 503, message: 'private response' })
    await Sentry.flush()
    const events = payloads('event')
    expect(events).toHaveLength(1)
    expect(events[0].tags).toMatchObject({ pathname: '/api/ratings/', method: 'POST', status: 503 })
    expect(JSON.stringify(events)).not.toMatch(/private|hidden/)
  })

  it('captures network failure while rethrowing the original error', async () => {
    const failure = new TypeError('Failed to fetch')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(failure))
    await expect(apiRequest('/api/categories/')).rejects.toBe(failure)
    await Sentry.flush()
    expect(payloads('event')).toHaveLength(1)
  })

  it.each([400, 401, 403, 404, 429])('does not capture expected HTTP %i', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status })))
    await expect(apiRequest('/api/auth/login/')).rejects.toMatchObject({ status })
    await Sentry.flush()
    expect(payloads('event')).toHaveLength(0)
  })

  it('excludes health failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Offline')))
    await expect(apiRequest('/api/health/')).rejects.toThrow('Offline')
    await Sentry.flush()
    expect(payloads('event')).toHaveLength(0)
  })
})

describe('session timing', () => {
  it.each(['ready', 'failed', 'empty', 'cancelled'] as const)('ends one span with outcome %s', async (outcome) => {
    startSessionTiming()
    startSessionTiming()
    withSessionTiming(() => Sentry.startSpan({ name: 'POST /api/sessions/', op: 'http.client' }, () => {}))
    finishSessionTiming(outcome)
    finishSessionTiming(outcome)
    await Sentry.flush()
    const transactions = payloads('transaction')
    expect(transactions).toHaveLength(1)
    expect(transactions[0].transaction).toBe('study.session_ready')
    expect(transactions[0].contexts?.trace?.data?.['study.outcome']).toBe(outcome)
    expect(transactions[0].contexts?.trace?.status).toBe(
      outcome === 'failed' ? 'internal_error' : outcome === 'cancelled' ? 'cancelled' : 'ok',
    )
    expect(transactions[0].spans).toHaveLength(1)
  })
})

describe('initialization', () => {
  it('does not initialize without a DSN', () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')
    const client = Sentry.getClient()
    initializeMonitoring()
    expect(Sentry.getClient()).toBe(client)
  })

  it('uses explicit settings and only propagates traces to the same-origin API', async () => {
    await Sentry.close()
    vi.stubEnv('VITE_SENTRY_DSN', 'https://public@example.com/1')
    vi.stubEnv('VITE_SENTRY_RELEASE', 'commit-sha')
    vi.stubEnv('VITE_SENTRY_ENVIRONMENT', 'production')
    vi.stubEnv('VITE_SENTRY_TRACES_SAMPLE_RATE', '0.25')
    initializeMonitoring()
    const options = Sentry.getClient()!.getOptions()
    expect(options).toMatchObject({ release: 'commit-sha', environment: 'production', tracesSampleRate: 0.25 })
    const targets = options.tracePropagationTargets as RegExp[]
    expect(targets.some((target) => target.test('/api/sessions/'))).toBe(true)
    expect(targets.some((target) => target.test(`${window.location.origin}/api/sessions/`))).toBe(true)
    expect(targets.some((target) => target.test('https://elsewhere.example/api/sessions/'))).toBe(false)
    expect(options.dataCollection).toMatchObject({ userInfo: false, httpBodies: [], cookies: false })
    expect(options.integrations.map((integration) => integration.name)).not.toContain('Breadcrumbs')
  })
})
