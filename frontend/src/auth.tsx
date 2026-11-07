import { createContext, type ComponentChildren } from 'preact'
import { useContext, useEffect, useState } from 'preact/hooks'
import { ApiError, checkHealth, fetchMe, type AuthUser } from './api'
import {
  clearOfflineStore,
  readOfflineUser,
  syncOfflineUser,
  type OfflineCachedUser
} from './offlineStore'
import { stopOfflinePrefetch } from './offlinePrefetch'

type AuthContextValue = {
  ready: boolean
  user: AuthUser | null
  bootError: string | null
  offline: boolean
  connectionLost: boolean
  hasOfflineCache: boolean
  setUser: (user: AuthUser) => void
  clearUser: () => void
  enterOffline: () => void
  retryConnection: () => Promise<boolean>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function userFromCache (cached: OfflineCachedUser): AuthUser {
  return {
    authenticated: true,
    email: cached.email,
    proficiency_level: cached.proficiency_level
  }
}

export function AuthProvider ({ children }: { children: ComponentChildren }) {
  const [ready, setReady] = useState(false)
  const [user, setUserState] = useState<AuthUser | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)
  const [offline, setOffline] = useState(false)
  const [connectionLost, setConnectionLost] = useState(false)
  const [hasOfflineCache, setHasOfflineCache] = useState(
    () => readOfflineUser() !== null
  )

  useEffect(() => {
    let cancelled = false

    async function loadSession () {
      try {
        const me = await fetchMe()
        if (cancelled) return
        if (me.authenticated) {
          syncOfflineUser({
            email: me.email,
            proficiency_level: me.proficiency_level
          })
          setHasOfflineCache(true)
          setUserState(me)
        } else {
          setUserState(null)
        }
        setOffline(false)
        setConnectionLost(false)
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          setUserState(null)
          return
        }
        const healthy = await checkHealth()
        if (cancelled) return
        if (!healthy) {
          const cached = readOfflineUser()
          setHasOfflineCache(cached !== null)
          setConnectionLost(true)
          setOffline(false)
          setUserState(cached ? userFromCache(cached) : null)
          return
        }
        setBootError(err instanceof Error ? err.message : 'Failed to reach API')
        setUserState(null)
      } finally {
        if (!cancelled) setReady(true)
      }
    }

    loadSession().catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  function setUser (next: AuthUser) {
    setBootError(null)
    setConnectionLost(false)
    setOffline(false)
    syncOfflineUser({
      email: next.email,
      proficiency_level: next.proficiency_level
    })
    setHasOfflineCache(true)
    setUserState(next)
  }

  function clearUser () {
    stopOfflinePrefetch()
    clearOfflineStore()
    setHasOfflineCache(false)
    setOffline(false)
    setConnectionLost(false)
    setUserState(null)
  }

  function enterOffline () {
    const cached = readOfflineUser()
    if (!cached) return
    setUserState(userFromCache(cached))
    setOffline(true)
    setConnectionLost(false)
    setBootError(null)
  }

  async function retryConnection (): Promise<boolean> {
    const healthy = await checkHealth()
    if (!healthy) return false
    try {
      const me = await fetchMe()
      if (me.authenticated) {
        syncOfflineUser({
          email: me.email,
          proficiency_level: me.proficiency_level
        })
        setHasOfflineCache(true)
        setUserState(me)
      } else {
        setUserState(null)
      }
      setOffline(false)
      setConnectionLost(false)
      setBootError(null)
      return true
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setUserState(null)
        setOffline(false)
        setConnectionLost(false)
        return true
      }
      return false
    }
  }

  return (
    <AuthContext.Provider
      value={{
        ready,
        user,
        bootError,
        offline,
        connectionLost,
        hasOfflineCache,
        setUser,
        clearUser,
        enterOffline,
        retryConnection
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth (): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return value
}
