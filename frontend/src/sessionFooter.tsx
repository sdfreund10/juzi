import { useState } from 'preact/hooks'
import { ApiError, logout } from './api'
import { useAuth } from './auth'
import { isIosDevice, isStandaloneDisplay } from './platform'
import { navigate } from './routes'

export function SessionFooter() {
  const { user, clearUser } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [signingOut, setSigningOut] = useState(false)
  const showInstallLink = isIosDevice() && !isStandaloneDisplay()

  if (!user) return null

  async function onSignOut() {
    setError(null)
    setSigningOut(true)
    try {
      await logout()
      clearUser()
      navigate({ name: 'home' }, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearUser()
        navigate({ name: 'home' }, { replace: true })
        return
      }
      setError('Could not sign out. Try again.')
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <>
      {error && (
        <p class="error" role="alert" aria-live="polite">
          {error}
        </p>
      )}
      <footer class="session-footer">
        <span class="session-email">{user.email}</span>
        {showInstallLink && (
          <button
            type="button"
            class="link-btn"
            onClick={() => navigate({ name: 'install' })}
          >
            Add to Home Screen
          </button>
        )}
        <button
          type="button"
          class="link-btn"
          onClick={onSignOut}
          disabled={signingOut}
        >
          {signingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </footer>
    </>
  )
}
