import { createContext, type ComponentChildren } from 'preact'
import { useContext, useEffect, useState } from 'preact/hooks'
import { ApiError, fetchMe, type AuthUser } from './api'

type AuthContextValue = {
  ready: boolean
  user: AuthUser | null
  bootError: string | null
  setUser: (user: AuthUser) => void
  clearUser: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ComponentChildren }) {
  const [ready, setReady] = useState(false)
  const [user, setUserState] = useState<AuthUser | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadSession() {
      try {
        const me = await fetchMe()
        if (cancelled) return
        setUserState(me.authenticated ? me : null)
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          setUserState(null)
          return
        }
        setBootError(err instanceof Error ? err.message : 'Failed to reach API')
        setUserState(null)
      } finally {
        if (!cancelled) setReady(true)
      }
    }

    void loadSession()
    return () => {
      cancelled = true
    }
  }, [])

  function setUser(next: AuthUser) {
    setBootError(null)
    setUserState(next)
  }

  function clearUser() {
    setUserState(null)
  }

  return (
    <AuthContext.Provider value={{ ready, user, bootError, setUser, clearUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return value
}
