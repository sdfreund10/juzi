import { useEffect } from 'preact/hooks'
import './app.css'
import { AuthProvider, useAuth } from './auth'
import { Brand } from './brand'
import { Decks } from './decks'
import { DifficultyStep } from './difficulty'
import { Install } from './install'
import { Login } from './login'
import { navigate } from './routes'
import { SessionFooter } from './sessionFooter'
import { ProficiencyStep } from './proficiency'
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

function ServiceUnavailable() {
  return (
    <main class="app">
      <h1 class="title">Service unavailable</h1>
      <p class="lede">juzi cannot reach the server right now. Try again in a moment.</p>
      <div class="picker-actions">
        <button type="button" class="cta" onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    </main>
  )
}

function AppShell() {
  const { ready, user, bootError, serviceUnavailable, setUser } = useAuth()
  const route = useRoute()

  useEffect(() => {
    if (ready && !user && !serviceUnavailable && route.name !== 'home') {
      navigate({ name: 'home' }, { replace: true })
    }
  }, [ready, user, serviceUnavailable, route.name])

  useEffect(() => {
    if (!ready || !user || serviceUnavailable) return
    if (user.proficiency_level === null && route.name !== 'proficiency') {
      navigate({ name: 'proficiency' }, { replace: true })
    }
  }, [ready, user, serviceUnavailable, route.name])

  if (!ready) {
    return (
      <main class="app">
        <Brand />
        <p class="building-status">Loading…</p>
      </main>
    )
  }

  if (serviceUnavailable) {
    return <ServiceUnavailable />
  }

  if (!user) {
    return <Login bootError={bootError} onSuccess={setUser} />
  }

  if (user.proficiency_level === null && route.name !== 'proficiency') {
    return (
      <main class="app">
        <Brand />
        <p class="building-status">Loading…</p>
      </main>
    )
  }

  const isStudy = route.name === 'session'

  return (
    <main class={`app${isStudy ? ' study' : ''}`}>
      {route.name === 'proficiency' ? (
        <ProficiencyStep />
      ) : route.name === 'session-new' ? (
        <DifficultyStep categoryId={route.categoryId} />
      ) : isStudy ? (
        <Study
          categoryId={route.categoryId}
          difficulties={route.difficulties}
        />
      ) : route.name === 'install' ? (
        <Install />
      ) : (
        <Decks />
      )}
      {route.name === 'home' && <SessionFooter />}
    </main>
  )
}
