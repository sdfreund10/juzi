import type { Category } from './api'

export const PINNED_DECK_IDS_KEY = 'juzi.pinnedDeckIds'

export function decksMatchingName (
  categories: Category[],
  query: string
): Category[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return categories
  return categories.filter((category) =>
    category.name.toLowerCase().includes(needle)
  )
}

export function recentlyPracticedDecks (
  categories: Category[],
  limit = 3
): Category[] {
  return categories
    .filter((category) => category.last_practiced_at !== null)
    .sort((a, b) => {
      const aAt = a.last_practiced_at ?? ''
      const bAt = b.last_practiced_at ?? ''
      return bAt.localeCompare(aAt)
    })
    .slice(0, limit)
}

export function readPinnedDeckIds (): number[] {
  const raw = localStorage.getItem(PINNED_DECK_IDS_KEY)
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (value): value is number =>
        typeof value === 'number' && Number.isInteger(value)
    )
  } catch {
    return []
  }
}

export function writePinnedDeckIds (ids: number[]): void {
  localStorage.setItem(PINNED_DECK_IDS_KEY, JSON.stringify(ids))
}

export function togglePinnedDeckId (ids: number[], id: number): number[] {
  return ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id]
}

export function pinnedDecks (
  categories: Category[],
  pinnedIds: number[]
): Category[] {
  const byId = new Map(categories.map((category) => [category.id, category]))
  return pinnedIds.flatMap((id) => {
    const category = byId.get(id)
    return category ? [category] : []
  })
}
