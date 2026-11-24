import { useEffect, useState } from 'preact/hooks'
import {
  ApiError,
  fetchLearnerScore,
  type LearnerScoreSnapshot
} from './api'
import { useAuth } from './auth'

export function useLearnerScore (): {
  snapshot: LearnerScoreSnapshot | null
  } {
  const { user, offline, clearUser } = useAuth()
  const [snapshot, setSnapshot] = useState<LearnerScoreSnapshot | null>(null)

  useEffect(() => {
    if (!user || offline) {
      setSnapshot(null)
      return
    }

    let cancelled = false

    async function load () {
      try {
        const next = await fetchLearnerScore()
        if (!cancelled) setSnapshot(next)
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          clearUser()
          return
        }
        setSnapshot(null)
      }
    }

    load().catch(() => {})
    return () => {
      cancelled = true
    }
  }, [user, offline])

  return { snapshot }
}
