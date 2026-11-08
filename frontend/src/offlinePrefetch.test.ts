import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSession, type Category, type StudySession } from './api'
import { PINNED_DECK_IDS_KEY, writePinnedDeckIds } from './deckList'
import {
  beginLearnerSessionBuild,
  endLearnerSessionBuild,
  prefetchCandidateIds,
  startOfflinePrefetch,
  stopOfflinePrefetch
} from './offlinePrefetch'
import {
  clearOfflineStore,
  offlineDeckCount,
  readOfflineDecks
} from './offlineStore'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return {
    ...actual,
    createSession: vi.fn()
  }
})

function category (
  partial: Partial<Category> & Pick<Category, 'id' | 'name'>
): Category {
  return {
    novice_count: 1,
    intermediate_count: 0,
    advanced_count: 0,
    expert_count: 0,
    last_practiced_at: null,
    ...partial
  }
}

function session (categoryId: number): StudySession {
  return {
    category: { id: categoryId, name: `Deck ${categoryId}` },
    difficulties: ['novice'],
    total: 1,
    cards: [
      {
        word_id: categoryId,
        mode: 'pinyin_to_en',
        answer_chinese: '字',
        answer_pinyin: 'zì',
        answer_english: 'character',
        example_chinese: '',
        example_pinyin: '',
        example_english: '',
        progress: {
          easy_streak: 0,
          easy_count: 0,
          due_on: null,
          last_practiced_at: null
        }
      }
    ]
  }
}

beforeEach(() => {
  clearOfflineStore()
  stopOfflinePrefetch()
  localStorage.removeItem(PINNED_DECK_IDS_KEY)
  vi.mocked(createSession).mockReset()
})

afterEach(() => {
  stopOfflinePrefetch()
  clearOfflineStore()
  localStorage.removeItem(PINNED_DECK_IDS_KEY)
})

describe('prefetchCandidateIds', () => {
  it('orders pinned, then recent, then the rest', () => {
    const categories = [
      category({ id: 1, name: 'A', last_practiced_at: '2026-01-01T00:00:00Z' }),
      category({ id: 2, name: 'B', last_practiced_at: '2026-02-01T00:00:00Z' }),
      category({ id: 3, name: 'C' }),
      category({ id: 4, name: 'D' })
    ]
    writePinnedDeckIds([3])

    expect(prefetchCandidateIds(categories)).toEqual([3, 2, 1, 4])
  })
})

describe('startOfflinePrefetch', () => {
  it('fills missing decks one at a time at the proficiency band', async () => {
    const categories = [
      category({ id: 1, name: 'A' }),
      category({ id: 2, name: 'B' })
    ]
    vi.mocked(createSession)
      .mockResolvedValueOnce(session(1))
      .mockResolvedValueOnce(session(2))

    startOfflinePrefetch(categories, 'novice')
    await vi.waitFor(() => expect(offlineDeckCount()).toBe(2))

    expect(createSession).toHaveBeenCalledTimes(2)
    expect(createSession).toHaveBeenNthCalledWith(1, 1, ['novice'])
    expect(createSession).toHaveBeenNthCalledWith(2, 2, ['novice'])
    expect(readOfflineDecks().every((entry) => entry.source === 'prefetch')).toBe(
      true
    )
  })

  it('skips empty sessions and silent failures', async () => {
    const categories = [
      category({ id: 1, name: 'A' }),
      category({ id: 2, name: 'B' }),
      category({ id: 3, name: 'C' })
    ]
    vi.mocked(createSession)
      .mockResolvedValueOnce({
        ...session(1),
        total: 0,
        cards: []
      })
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(session(3))

    startOfflinePrefetch(categories, 'novice')
    await vi.waitFor(() => expect(offlineDeckCount()).toBe(1))

    expect(readOfflineDecks()[0]?.categoryId).toBe(3)
  })

  it('waits while a learner session build is in flight', async () => {
    const categories = [category({ id: 1, name: 'A' })]
    let resolveSession!: (value: StudySession) => void
    vi.mocked(createSession).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSession = resolve
        })
    )

    beginLearnerSessionBuild()
    startOfflinePrefetch(categories, 'novice')
    expect(createSession).not.toHaveBeenCalled()

    endLearnerSessionBuild()
    await vi.waitFor(() => expect(createSession).toHaveBeenCalledTimes(1))
    resolveSession(session(1))
    await vi.waitFor(() => expect(offlineDeckCount()).toBe(1))
  })

  it('resumes a prefetch queued after a running fill is stopped', async () => {
    const categories = [category({ id: 1, name: 'A' })]
    let releaseFirst!: (value: StudySession) => void
    vi.mocked(createSession)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            releaseFirst = resolve
          })
      )
      .mockResolvedValue(session(1))

    startOfflinePrefetch(categories, 'novice')
    await vi.waitFor(() => expect(createSession).toHaveBeenCalledTimes(1))

    beginLearnerSessionBuild()
    stopOfflinePrefetch()
    releaseFirst(session(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(offlineDeckCount()).toBe(0)

    startOfflinePrefetch(categories, 'novice')
    expect(createSession).toHaveBeenCalledTimes(1)

    endLearnerSessionBuild()
    await vi.waitFor(() => expect(createSession).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(offlineDeckCount()).toBe(1))
  })
})
