import type { Category } from './api'

export function decksMatchingName(
  categories: Category[],
  query: string,
): Category[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return categories
  return categories.filter((category) =>
    category.name.toLowerCase().includes(needle),
  )
}

export function recentlyPracticedDecks(
  categories: Category[],
  limit = 3,
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
