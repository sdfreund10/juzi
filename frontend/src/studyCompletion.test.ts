import { h, render } from 'preact'
import { act } from 'preact/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Study } from './study'
import type { StudyCard } from './api'
import { setToastHandler } from './toast'

vi.mock('./useCategories', () => ({
  useCategory: () => ({
    category: { id: 1, name: 'Test deck' },
    ready: true,
    missing: false,
    error: null
  })
}))

vi.mock('./auth', () => ({
  useAuth: () => ({
    ready: true,
    user: {
      authenticated: true,
      email: 't@example.com',
      proficiency_level: 'novice'
    },
    bootError: null,
    offline: false,
    connectionLost: false,
    hasOfflineCache: true,
    setUser: () => {},
    clearUser: () => {},
    enterOffline: () => {},
    retryConnection: async () => true
  })
}))

const emptyProgress = {
  easy_streak: 0,
  easy_count: 0,
  due_on: null,
  last_practiced_at: null
}
const ratedAt = '2026-10-15T12:00:00.000Z'
const cards: StudyCard[] = [1, 2].map((id) => ({
  word_id: id,
  mode: 'pinyin_to_en',
  answer_chinese: `word-${id}`,
  answer_pinyin: `pinyin-${id}`,
  answer_english: `answer-${id}`,
  example_chinese: '',
  example_pinyin: '',
  example_english: '',
  progress: emptyProgress
}))

let host: HTMLDivElement
let fetchMock: ReturnType<typeof vi.fn>

function json (body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  setToastHandler(() => {})
  vi.spyOn(Date.prototype, 'toISOString').mockReturnValue(ratedAt)
  vi.spyOn(crypto, 'randomUUID').mockReturnValue(
    '11111111-1111-1111-1111-111111111111'
  )
  fetchMock = vi.fn((path: string) => {
    if (path === '/api/learner-score/completions/') {
      return Promise.resolve(
        json({
          date: '2026-10-15',
          starting_score: 0,
          score: 10,
          points: 10,
          client_id: '11111111-1111-1111-1111-111111111111'
        })
      )
    }
    if (path === '/api/ratings/undo/') {
      return Promise.resolve(new Response(null, { status: 204 }))
    }
    return Promise.resolve(json({}))
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(async () => {
  await act(() => render(null, host))
  host.remove()
  setToastHandler(null)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function mount (sessionCards = cards) {
  fetchMock.mockResolvedValueOnce(
    json({
      category: { id: 1, name: 'Test deck' },
      difficulties: ['novice'],
      total: sessionCards.length,
      cards: sessionCards
    })
  )
  await act(() =>
    render(h(Study, { categoryId: 1, difficulties: ['novice'] }), host)
  )
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function click (selector: string) {
  const target = host.querySelector<HTMLElement>(selector)
  expect(target).not.toBeNull()
  await act(async () => {
    target!.click()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function gradeEasy () {
  await click('.reveal-target')
  await click('.grade-zone.easy')
}

function completionCalls () {
  return fetchMock.mock.calls.filter(
    ([path]) => path === '/api/learner-score/completions/'
  )
}

it('posts a completion and shows the score bump when the deck finishes', async () => {
  await mount()
  await gradeEasy()
  await gradeEasy()

  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  expect(completionCalls()).toHaveLength(1)
  expect(completionCalls()[0]?.[1]).toEqual(
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        difficulties: ['novice'],
        client_id: '11111111-1111-1111-1111-111111111111'
      })
    })
  )
  expect(host.textContent).toContain('Deck complete')
  expect(host.textContent).toContain('+10')
  expect(host.textContent).toContain('Learner score increased')
})

it('reuses the same completion client id after undo and finish again', async () => {
  await mount([cards[0]!])
  await gradeEasy()
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  expect(completionCalls()).toHaveLength(1)
  const firstBody = completionCalls()[0]?.[1]?.body

  await click('.study-undo')
  await click('.grade-zone.easy')
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  // Grade posts again; server idempotency keeps the score from double-counting.
  expect(completionCalls()).toHaveLength(2)
  expect(completionCalls()[1]?.[1]?.body).toBe(firstBody)
  expect(host.textContent).toContain('Deck complete')
})

it('skips the completion post when the last rating fails', async () => {
  await mount([cards[0]!])
  fetchMock.mockImplementation((path: string) => {
    if (path === '/api/ratings/') {
      return Promise.resolve(json({}, 500))
    }
    if (path === '/api/learner-score/completions/') {
      return Promise.resolve(
        json({
          date: '2026-10-15',
          starting_score: 0,
          score: 10,
          points: 10,
          client_id: '11111111-1111-1111-1111-111111111111'
        })
      )
    }
    return Promise.resolve(json({}))
  })

  await gradeEasy()
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  expect(completionCalls()).toHaveLength(0)
  expect(host.textContent).toContain('Deck complete')
  expect(host.textContent).not.toContain('+10')
})

it('skips the bump when the completion request fails', async () => {
  await mount([cards[0]!])
  fetchMock.mockImplementation((path: string) => {
    if (path === '/api/learner-score/completions/') {
      return Promise.resolve(json({}, 500))
    }
    return Promise.resolve(json({}))
  })

  await gradeEasy()
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  expect(completionCalls()).toHaveLength(1)
  expect(host.textContent).toContain('Deck complete')
  expect(host.textContent).not.toContain('+10')
})
