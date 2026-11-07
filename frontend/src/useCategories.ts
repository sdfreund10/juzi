import { useEffect, useState } from 'preact/hooks'
import { ApiError, fetchCategories, type Category } from './api'
import { useAuth } from './auth'
import { startOfflinePrefetch, stopOfflinePrefetch } from './offlinePrefetch'
import {
  categoriesAvailableOffline,
  readOfflineCategories,
  writeOfflineCategories
} from './offlineStore'

export function useCategories (): {
  categories: Category[] | null
  error: string | null
  } {
  const { user, offline, clearUser } = useAuth()
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) {
      setCategories(null)
      setError(null)
      stopOfflinePrefetch()
      return
    }

    if (offline) {
      const rows = categoriesAvailableOffline()
      setCategories(rows)
      setError(rows ? null : 'No decks saved for offline study.')
      return
    }

    let cancelled = false

    async function load () {
      try {
        const rows = await fetchCategories()
        if (cancelled) return
        writeOfflineCategories(rows)
        setCategories(rows)
        setError(null)
        startOfflinePrefetch(rows, user!.proficiency_level)
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          clearUser()
          return
        }
        const cached = readOfflineCategories()
        if (cached) {
          setCategories(cached)
          setError(null)
          return
        }
        setError('Could not load decks. Try again.')
        setCategories(null)
      }
    }

    load().catch(() => {})
    return () => {
      cancelled = true
    }
  }, [user, offline])

  return { categories, error }
}

export function useCategory (categoryId: number): {
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
    missing: ready && error === null && category === null,
    error
  }
}
