import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest, checkHealth, flagWord, login, rateCard } from './api'
import { setToastHandler } from './toast'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
  setToastHandler(null)
})

function jsonResponse (status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  })
}

describe('apiRequest', () => {
  it('returns JSON on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { authenticated: false, email: null, proficiency_level: null })
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest('/api/auth/me/')).resolves.toEqual({
      authenticated: false,
      email: null,
      proficiency_level: null
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/me/',
      expect.objectContaining({
        method: 'GET',
        credentials: 'same-origin'
      })
    )
  })

  it('surfaces string detail from error bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, { detail: 'Invalid email or password.' })
      )
    )

    const err = await apiRequest('/api/auth/login/', {
      method: 'POST',
      body: { email: 'a@b.com', password: 'x' }
    }).catch((e: unknown) => e)

    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({
      status: 400,
      message: 'Invalid email or password.'
    })
  })

  it('surfaces the first DRF field error message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, { email: ['Enter a valid email address.'] })
      )
    )

    await expect(
      apiRequest('/api/auth/login/', {
        method: 'POST',
        body: { email: 'nope', password: 'x' }
      })
    ).rejects.toMatchObject({
      status: 400,
      message: 'Enter a valid email address.'
    })
  })

  it('falls back when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('plain fail', { status: 500 }))
    )

    await expect(apiRequest('/api/auth/me/')).rejects.toMatchObject({
      status: 500,
      message: 'Request failed'
    })
  })

  it('sends the CSRF token on unsafe methods', async () => {
    document.cookie = 'csrftoken=test-csrf; path=/'
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        authenticated: true,
        email: 'a@b.com',
        proficiency_level: null
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    await login('a@b.com', 'secret')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login/',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-CSRFToken': 'test-csrf',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify({ email: 'a@b.com', password: 'secret' })
      })
    )
  })

  it('toasts when a request fails', async () => {
    const toasts: string[] = []
    setToastHandler((message) => toasts.push(message))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(500, { detail: 'Server error' }))
    )

    await expect(
      apiRequest('/api/ratings/', { method: 'POST', body: {}, toast: true })
    ).rejects.toBeInstanceOf(ApiError)
    expect(toasts).toEqual(['Server error'])
  })

  it('toasts when the network is unreachable', async () => {
    const toasts: string[] = []
    setToastHandler((message) => toasts.push(message))
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(
      apiRequest('/api/ratings/', { method: 'POST', body: {}, toast: true })
    ).rejects.toThrow('Failed to fetch')
    expect(toasts).toEqual(['Could not reach the server.'])
  })

  it('does not toast by default', async () => {
    const toasts: string[] = []
    setToastHandler((message) => toasts.push(message))
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(500, { detail: 'Server error' }))
    )

    await expect(apiRequest('/api/auth/me/')).rejects.toBeInstanceOf(ApiError)
    expect(toasts).toEqual([])
  })
})

describe('rateCard', () => {
  it.each([
    [401, 'Your session expired. Sign in again to save progress.'],
    [500, 'Couldn’t save your progress. You can keep studying.']
  ])('shows learner-facing copy for HTTP %i without a duplicate toast', async (status, message) => {
    const toasts: string[] = []
    setToastHandler((toast) => toasts.push(toast))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse(status, { detail: 'Internal API wording' })
    ))

    await expect(rateCard(1, 'easy')).rejects.toMatchObject({ status })
    expect(toasts).toEqual([message])
  })

  it('explains a network failure without promising a later sync', async () => {
    const toasts: string[] = []
    setToastHandler((message) => toasts.push(message))
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(rateCard(1, 'hard')).rejects.toThrow('Failed to fetch')
    expect(toasts).toEqual(['Couldn’t save your progress. You can keep studying.'])
  })
})

describe('flagWord', () => {
  it('posts word_id and toasts on success', async () => {
    const toasts: string[] = []
    setToastHandler((toast) => toasts.push(toast))
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    document.cookie = 'csrftoken=test-token; path=/'

    await flagWord(42)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/word-flags/',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        body: JSON.stringify({ word_id: 42 })
      })
    )
    expect(toasts).toEqual(['Marked for review'])
  })

  it.each([
    [401, 'Your session expired. Sign in again.'],
    [500, 'Couldn’t flag this card. Try again.']
  ])('shows learner-facing copy for HTTP %i', async (status, message) => {
    const toasts: string[] = []
    setToastHandler((toast) => toasts.push(toast))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse(status, { detail: 'Internal API wording' })
    ))

    await expect(flagWord(1)).rejects.toMatchObject({ status })
    expect(toasts).toEqual([message])
  })
})

describe('checkHealth', () => {
  it('returns true when /api/health/ is ok', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { status: 'ok', service: 'juzi', database: 'connected' })
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(checkHealth()).resolves.toBe(true)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health/',
      expect.objectContaining({ method: 'GET', credentials: 'same-origin' })
    )
  })

  it('returns false when /api/health/ fails or is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(500, { status: 'error', service: 'juzi', database: 'disconnected' })
      )
    )
    await expect(checkHealth()).resolves.toBe(false)

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(checkHealth()).resolves.toBe(false)
  })
})
