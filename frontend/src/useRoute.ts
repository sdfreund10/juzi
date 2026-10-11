import { useEffect, useState } from 'preact/hooks'
import { parsePath, pathFor, type Route } from './routes'

function readRoute(): Route {
  return parsePath(window.location.pathname)
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(readRoute)

  useEffect(() => {
    function onPopState() {
      setRoute(readRoute())
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    const canonical = pathFor(route)
    if (canonical !== window.location.pathname) {
      window.history.replaceState(null, '', canonical)
    }
  }, [route])

  return route
}
