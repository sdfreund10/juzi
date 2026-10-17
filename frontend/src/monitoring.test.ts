import * as Sentry from '@sentry/browser'
import { afterEach, expect, it, vi } from 'vitest'
import { apiRequest } from './api'

vi.mock('@sentry/browser', () => ({ captureException: vi.fn() }))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

it('reports server failures with the request method, pathname, and status', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 503 })))
  await expect(apiRequest('/api/ratings/', { method: 'POST', body: { grade: 'easy' } }))
    .rejects.toMatchObject({ status: 503 })
  expect(Sentry.captureException).toHaveBeenCalledWith(
    expect.objectContaining({ message: 'API server failure' }),
    expect.objectContaining({ tags: { method: 'POST', pathname: '/api/ratings/', status: 503 } })
  )
})

it('reports a network failure and preserves the original error', async () => {
  const failure = new TypeError('Failed to fetch')
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(failure))
  await expect(apiRequest('/api/categories/')).rejects.toBe(failure)
  expect(Sentry.captureException).toHaveBeenCalledWith(
    expect.objectContaining({ message: 'API network failure' }),
    expect.objectContaining({ tags: { method: 'GET', pathname: '/api/categories/' } })
  )
})

it.each([400, 401, 403, 404, 429])('does not report expected HTTP %i', async (status) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status })))
  await expect(apiRequest('/api/auth/login/')).rejects.toMatchObject({ status })
  expect(Sentry.captureException).not.toHaveBeenCalled()
})

it('does not report health-check failures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Offline')))
  await expect(apiRequest('/api/health/')).rejects.toThrow('Offline')
  expect(Sentry.captureException).not.toHaveBeenCalled()
})
