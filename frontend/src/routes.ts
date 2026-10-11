import type { Difficulty } from './api'

export const DIFFICULTY_ORDER: Difficulty[] = ['beginner', 'intermediate', 'advanced']

const DIFFICULTY_SET = new Set<string>(DIFFICULTY_ORDER)

export type Route =
  | { name: 'home' }
  | { name: 'session-new'; categoryId: number }
  | { name: 'session'; categoryId: number; difficulties: Difficulty[] }

export function serializeDifficulties(difficulties: Difficulty[]): string {
  return DIFFICULTY_ORDER.filter((id) => difficulties.includes(id)).join('-')
}

export function parseDifficulties(slug: string): Difficulty[] | null {
  if (!slug) return null
  const parts = slug.split('-')
  if (parts.length === 0) return null
  const seen = new Set<string>()
  for (const part of parts) {
    if (!DIFFICULTY_SET.has(part) || seen.has(part)) return null
    seen.add(part)
  }
  return DIFFICULTY_ORDER.filter((id) => seen.has(id))
}

export function parsePath(pathname: string): Route {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (path === '/') return { name: 'home' }

  const match = path.match(/^\/category\/(\d+)\/sessions\/([^/]+)$/)
  if (!match) return { name: 'home' }

  const categoryId = Number(match[1])
  if (!Number.isInteger(categoryId) || categoryId < 1) return { name: 'home' }

  const segment = match[2]
  if (segment === 'new') {
    return { name: 'session-new', categoryId }
  }

  const difficulties = parseDifficulties(segment)
  if (!difficulties || difficulties.length === 0) return { name: 'home' }

  return { name: 'session', categoryId, difficulties }
}

export function pathFor(route: Route): string {
  switch (route.name) {
    case 'home':
      return '/'
    case 'session-new':
      return `/category/${route.categoryId}/sessions/new`
    case 'session':
      return `/category/${route.categoryId}/sessions/${serializeDifficulties(route.difficulties)}`
  }
}

export function navigate(route: Route, options: { replace?: boolean } = {}): void {
  const next = pathFor(route)
  if (next === window.location.pathname) return
  if (options.replace) {
    window.history.replaceState(null, '', next)
  } else {
    window.history.pushState(null, '', next)
  }
  window.dispatchEvent(new PopStateEvent('popstate'))
}
