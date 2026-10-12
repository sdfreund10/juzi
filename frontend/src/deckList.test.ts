import { describe, expect, it } from 'vitest'
import type { Category } from './api'
import { decksMatchingName, recentlyPracticedDecks } from './deckList'

function category(
  partial: Partial<Category> & Pick<Category, 'id' | 'name'>,
): Category {
  return {
    beginner_count: 0,
    intermediate_count: 0,
    advanced_count: 0,
    last_practiced_at: null,
    ...partial,
  }
}

describe('decksMatchingName', () => {
  const decks = [
    category({ id: 1, name: 'Food, Cooking & Dining' }),
    category({ id: 2, name: 'Numbers, Time & Measurement' }),
    category({ id: 3, name: 'Travel' }),
  ]

  it('returns all decks when the query is blank', () => {
    expect(decksMatchingName(decks, '  ')).toEqual(decks)
  })

  it('filters by case-insensitive name substring', () => {
    expect(decksMatchingName(decks, 'time')).toEqual([decks[1]])
  })

  it('returns an empty list when nothing matches', () => {
    expect(decksMatchingName(decks, 'xyz')).toEqual([])
  })
})

describe('recentlyPracticedDecks', () => {
  it('returns up to three decks ordered by most recent practice', () => {
    const decks = [
      category({
        id: 1,
        name: 'Old',
        last_practiced_at: '2026-01-01T10:00:00Z',
      }),
      category({ id: 2, name: 'Never' }),
      category({
        id: 3,
        name: 'Newest',
        last_practiced_at: '2026-03-01T10:00:00Z',
      }),
      category({
        id: 4,
        name: 'Middle',
        last_practiced_at: '2026-02-01T10:00:00Z',
      }),
      category({
        id: 5,
        name: 'Also recent',
        last_practiced_at: '2026-02-15T10:00:00Z',
      }),
    ]

    expect(recentlyPracticedDecks(decks).map((row) => row.id)).toEqual([
      3, 5, 4,
    ])
  })
})
