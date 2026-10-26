import { useEffect, useRef } from 'preact/hooks'
import './app.css'
import { AuthProvider, useAuth } from './auth'
import { Brand } from './brand'
import { CardById, CardLookup } from './cardAudit'
import { Decks } from './decks'
import { DifficultyStep } from './difficulty'
import { Install } from './install'
import { Login } from './login'
import { consumePendingReplaceNavigation, navigate, type Route } from './routes'
import { SessionFooter } from './sessionFooter'
import { ProficiencyStep } from './proficiency'
import {
  routeKey,
  screenMotion,
  type ScreenMotionKind
} from './screenMotion'
import { Study } from './study'
import { ToastHost } from './toast'
import { useRoute } from './useRoute'

export function App () {
  return (
    <AuthProvider>
      <AppShell />
      <ToastHost />
    </AuthProvider>
  )
}

function ServiceUnavailable () {
  return (
    <main class='app'>
      <h1 class='title'>Service unavailable</h1>
      <p class='lede'>juzi cannot reach the server right now. Try again in a moment.</p>
      <div class='picker-actions'>
        <button type='button' class='cta' onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    </main>
  )
}

function screenClass (motion: ScreenMotionKind): string {
  if (motion === 'none') return 'screen'
  return `screen screen-enter-${motion}`
}

function RoutedScreen ({ route }: { route: Route }) {
  const previousRoute = useRef<Route | null>(null)
  const previousKey = useRef<string | null>(null)
  const motionRef = useRef<ScreenMotionKind>('fade')
  const key = routeKey(route)

  if (previousKey.current !== key) {
    const skipStack = consumePendingReplaceNavigation()
    const from = previousRoute.current
    if (skipStack) {
      motionRef.current = 'none'
    } else if (from === null) {
      motionRef.current = 'fade'
    } else {
      motionRef.current = screenMotion(from, route)
    }
    previousRoute.current = route
    previousKey.current = key
  }

  const motion = motionRef.current
  const isStudy =
    route.name === 'session' ||
    route.name === 'card' ||
    route.name === 'card-lookup'
  let body
  if (route.name === 'proficiency') {
    body = <ProficiencyStep />
  } else if (route.name === 'session-new') {
    body = <DifficultyStep categoryId={route.categoryId} />
  } else if (route.name === 'session') {
    body = (
      <Study
        categoryId={route.categoryId}
        difficulties={route.difficulties}
      />
    )
  } else if (route.name === 'card') {
    body = <CardById mode={route.mode} wordId={route.wordId} />
  } else if (route.name === 'card-lookup') {
    body = <CardLookup mode={route.mode} chinese={route.chinese} />
  } else if (route.name === 'install') {
    body = <Install />
  } else {
    body = (
      <>
        <Decks />
        <SessionFooter />
      </>
    )
  }

  return (
    <main class={`app${isStudy ? ' study' : ''}`}>
      <div key={routeKey(route)} class={screenClass(motion)}>
        {body}
      </div>
    </main>
  )
}

function AppShell () {
  const { ready, user, bootError, serviceUnavailable, setUser } = useAuth()
  const route = useRoute()

  useEffect(() => {
    if (ready && !user && !serviceUnavailable && route.name !== 'home') {
      navigate({ name: 'home' }, { replace: true })
    }
  }, [ready, user, serviceUnavailable, route.name])

  useEffect(() => {
    if (!ready || !user || serviceUnavailable) return
    if (user.proficiency_level === null && route.name === 'home') {
      navigate({ name: 'proficiency' }, { replace: true })
    }
  }, [ready, user, serviceUnavailable, route.name])

  if (!ready) {
    return (
      <main class='app'>
        <Brand />
        <p class='building-status'>Loading…</p>
      </main>
    )
  }

  if (serviceUnavailable) {
    return <ServiceUnavailable />
  }

  if (!user) {
    return <Login bootError={bootError} onSuccess={setUser} />
  }

  if (user.proficiency_level === null && route.name === 'home') {
    return (
      <main class='app'>
        <Brand />
        <p class='building-status'>Loading…</p>
      </main>
    )
  }

  return <RoutedScreen route={route} />
}
