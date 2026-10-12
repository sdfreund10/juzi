import { describe, expect, it } from 'vitest'
import type { Category } from './api'
import { decksMatchingName } from './deckList'

function category(partial: Partial<Category> & Pick<Category, 'id' | 'name'>): Category {
  return {
    beginner_count: 0,
    intermediate_count: 0,
    advanced_count: 0,
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
