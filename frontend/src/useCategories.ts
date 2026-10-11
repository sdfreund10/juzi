import { useEffect, useState } from 'preact/hooks'
import { ApiError, fetchCategories, type Category } from './api'
import { useAuth } from './auth'

export function useCategories(): {
  categories: Category[] | null
  error: string | null
} {
  const { user, clearUser } = useAuth()
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) {
      setCategories(null)
      setError(null)
      return
    }

    let cancelled = false

    async function load() {
      try {
        const rows = await fetchCategories()
        if (!cancelled) {
          setCategories(rows)
          setError(null)
        }
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          clearUser()
          return
        }
        setError('Could not load decks. Try again.')
        setCategories([])
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [user])

  return { categories, error }
}

export function useCategory(categoryId: number): {
  category: Category | null
  ready: boolean
  missing: boolean
  error: string | null
} {
  const { categories, error } = useCategories()
  const ready = categories !== null
  const category = categories?.find((row) => row.id === categoryId) ?? null
  return {
    category,
    ready,
    missing: ready && category === null,
    error,
  }
}
