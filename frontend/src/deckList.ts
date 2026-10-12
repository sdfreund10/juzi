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
