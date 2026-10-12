import { useEffect } from 'preact/hooks'
import './app.css'
import { AuthProvider, useAuth } from './auth'
import { Decks } from './decks'
import { DifficultyStep } from './difficulty'
import { Login } from './login'
import { navigate } from './routes'
import { SessionFooter } from './sessionFooter'
import { Study } from './study'
import { ToastHost } from './toast'
import { useRoute } from './useRoute'

export function App() {
  return (
    <AuthProvider>
      <AppShell />
      <ToastHost />
    </AuthProvider>
  )
}

function AppShell() {
  const { ready, user, bootError, setUser } = useAuth()
  const route = useRoute()

  useEffect(() => {
    if (ready && !user && route.name !== 'home') {
      navigate({ name: 'home' }, { replace: true })
    }
  }, [ready, user, route.name])

  if (!ready) {
    return (
      <main class="app">
        <p class="building-status">Loading…</p>
      </main>
    )
  }

  if (!user) {
    return <Login bootError={bootError} onSuccess={setUser} />
  }

  const isStudy = route.name === 'session'

  return (
    <main class={`app${isStudy ? ' study' : ''}`}>
      {route.name === 'session-new' ? (
        <DifficultyStep categoryId={route.categoryId} />
      ) : isStudy ? (
        <Study
          categoryId={route.categoryId}
          difficulties={route.difficulties}
        />
      ) : (
        <Decks />
      )}
      <SessionFooter />
    </main>
  )
}
