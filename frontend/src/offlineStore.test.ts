import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StudySession } from './api'
import {
  OFFLINE_CATEGORIES_KEY,
  OFFLINE_DECKS_KEY,
  OFFLINE_DECK_LIMIT,
  OFFLINE_USER_KEY,
  cacheOfflineDeck,
  categoriesAvailableOffline,
  clearOfflineStore,
  findOfflineDeck,
  hasOfflineDeck,
  offlineDeckCount,
  readOfflineCategories,
  readOfflineDecks,
  readOfflineUser,
  syncOfflineUser,
  writeOfflineCategories
} from './offlineStore'

function session (
  categoryId: number,
  name = `Deck ${categoryId}`,
  difficulties: StudySession['difficulties'] = ['novice']
): StudySession {
  return {
    category: { id: categoryId, name },
    difficulties,
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

afterEach(() => {
  clearOfflineStore()
  vi.restoreAllMocks()
})

describe('syncOfflineUser', () => {
  it('writes the user and keeps the store for the same email', () => {
    syncOfflineUser({ email: 'a@example.com', proficiency_level: 'novice' })
    writeOfflineCategories([
      {
        id: 1,
        name: 'Food',
        novice_count: 1,
        intermediate_count: 0,
        advanced_count: 0,
        expert_count: 0,
        last_practiced_at: null
      }
    ])
    cacheOfflineDeck(session(1), 'studied')

    syncOfflineUser({ email: 'a@example.com', proficiency_level: 'advanced' })

    expect(readOfflineUser()).toEqual({
      email: 'a@example.com',
      proficiency_level: 'advanced'
    })
    expect(readOfflineCategories()).toHaveLength(1)
    expect(offlineDeckCount()).toBe(1)
  })

  it('clears the store when the email changes', () => {
    syncOfflineUser({ email: 'a@example.com', proficiency_level: 'novice' })
    writeOfflineCategories([
      {
        id: 1,
        name: 'Food',
        novice_count: 1,
        intermediate_count: 0,
        advanced_count: 0,
        expert_count: 0,
        last_practiced_at: null
      }
    ])
    cacheOfflineDeck(session(1), 'studied')

    syncOfflineUser({ email: 'b@example.com', proficiency_level: 'novice' })

    expect(readOfflineUser()?.email).toBe('b@example.com')
    expect(readOfflineCategories()).toBeNull()
    expect(offlineDeckCount()).toBe(0)
    expect(localStorage.getItem(OFFLINE_CATEGORIES_KEY)).toBeNull()
    expect(localStorage.getItem(OFFLINE_DECKS_KEY)).toBeNull()
  })
})

describe('categoriesAvailableOffline', () => {
  it('returns the stored category list', () => {
    writeOfflineCategories([
      {
        id: 1,
        name: 'Food',
        novice_count: 4,
        intermediate_count: 0,
        advanced_count: 0,
        expert_count: 0,
        last_practiced_at: null
      }
    ])

    expect(categoriesAvailableOffline()).toEqual([
      {
        id: 1,
        name: 'Food',
        novice_count: 4,
        intermediate_count: 0,
        advanced_count: 0,
        expert_count: 0,
        last_practiced_at: null
      }
    ])
  })

  it('derives one row per cached category when the category list is missing', () => {
    cacheOfflineDeck(session(2, 'Travel'), 'studied')
    cacheOfflineDeck(session(3, 'Food'), 'prefetch')

    expect(categoriesAvailableOffline()).toEqual([
      {
        id: 3,
        name: 'Food',
        novice_count: 0,
        intermediate_count: 0,
        advanced_count: 0,
        expert_count: 0,
        last_practiced_at: null
      },
      {
        id: 2,
        name: 'Travel',
        novice_count: 0,
        intermediate_count: 0,
        advanced_count: 0,
        expert_count: 0,
        last_practiced_at: null
      }
    ])
  })

  it('returns null when nothing is cached', () => {
    expect(categoriesAvailableOffline()).toBeNull()
  })
})

describe('cacheOfflineDeck', () => {
  it('skips empty sessions', () => {
    cacheOfflineDeck(
      {
        category: { id: 1, name: 'Empty' },
        difficulties: ['novice'],
        total: 0,
        cards: []
      },
      'studied'
    )
    expect(offlineDeckCount()).toBe(0)
  })

  it('replaces an existing deck and moves it to the front', () => {
    cacheOfflineDeck(session(1, 'One', ['novice']), 'prefetch')
    cacheOfflineDeck(session(2, 'Two', ['novice']), 'studied')
    cacheOfflineDeck(session(1, 'One refreshed', ['intermediate']), 'studied')

    const decks = readOfflineDecks()
    expect(decks).toHaveLength(2)
    expect(decks[0]?.categoryId).toBe(1)
    expect(decks[0]?.difficulties).toEqual(['intermediate'])
    expect(decks[0]?.source).toBe('studied')
    expect(decks[0]?.session.category.name).toBe('One refreshed')
    expect(decks[1]?.categoryId).toBe(2)
  })

  it('drops a prefetched deck before a studied deck when full', () => {
    for (let id = 1; id <= OFFLINE_DECK_LIMIT; id += 1) {
      cacheOfflineDeck(
        session(id),
        id === 1 ? 'prefetch' : 'studied'
      )
    }
    expect(offlineDeckCount()).toBe(OFFLINE_DECK_LIMIT)

    cacheOfflineDeck(session(99), 'studied')

    expect(offlineDeckCount()).toBe(OFFLINE_DECK_LIMIT)
    expect(hasOfflineDeck(1)).toBe(false)
    expect(hasOfflineDeck(2)).toBe(true)
    expect(hasOfflineDeck(99)).toBe(true)
  })

  it('drops the oldest studied deck when every entry was studied', () => {
    const stamp = vi.spyOn(Date.prototype, 'toISOString')
    for (let id = 1; id <= OFFLINE_DECK_LIMIT; id += 1) {
      stamp.mockReturnValue(
        `2026-01-${String(id).padStart(2, '0')}T00:00:00.000Z`
      )
      cacheOfflineDeck(session(id), 'studied')
    }

    stamp.mockReturnValue('2026-02-01T00:00:00.000Z')
    cacheOfflineDeck(session(99), 'studied')

    expect(hasOfflineDeck(1)).toBe(false)
    expect(hasOfflineDeck(99)).toBe(true)
    expect(offlineDeckCount()).toBe(OFFLINE_DECK_LIMIT)
  })

  it('retries once after dropping a prefetched deck when quota is exceeded', () => {
    cacheOfflineDeck(session(1), 'prefetch')
    cacheOfflineDeck(session(2), 'studied')

    const originalSetItem = localStorage.setItem.bind(localStorage)
    let attempts = 0
    vi.spyOn(localStorage, 'setItem').mockImplementation((key, value) => {
      if (key === OFFLINE_DECKS_KEY) {
        attempts += 1
        if (attempts === 1) {
          const err = new DOMException('quota', 'QuotaExceededError')
          throw err
        }
      }
      return originalSetItem(key, value)
    })

    cacheOfflineDeck(session(3), 'studied')

    expect(attempts).toBeGreaterThanOrEqual(2)
    expect(hasOfflineDeck(1)).toBe(false)
    expect(hasOfflineDeck(2)).toBe(true)
    expect(hasOfflineDeck(3)).toBe(true)
  })
})

describe('findOfflineDeck', () => {
  it('finds by category and optional difficulty set', () => {
    cacheOfflineDeck(session(1, 'One', ['novice', 'intermediate']), 'studied')

    expect(findOfflineDeck(1)?.session.category.name).toBe('One')
    expect(
      findOfflineDeck(1, ['novice', 'intermediate'])?.session.category.name
    ).toBe('One')
    expect(findOfflineDeck(1, ['novice'])).toBeNull()
    expect(findOfflineDeck(2)).toBeNull()
  })
})

describe('clearOfflineStore', () => {
  it('removes all offline keys', () => {
    syncOfflineUser({ email: 'a@example.com', proficiency_level: 'novice' })
    writeOfflineCategories([])
    cacheOfflineDeck(session(1), 'studied')

    clearOfflineStore()

    expect(localStorage.getItem(OFFLINE_USER_KEY)).toBeNull()
    expect(localStorage.getItem(OFFLINE_CATEGORIES_KEY)).toBeNull()
    expect(localStorage.getItem(OFFLINE_DECKS_KEY)).toBeNull()
  })
})
