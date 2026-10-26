import { serializeDifficulties, type Route } from './routes'

export type ScreenMotionKind = 'forward' | 'back' | 'fade' | 'none'

export function routeDepth (route: Route): number {
  switch (route.name) {
    case 'home':
      return 0
    case 'install':
    case 'proficiency':
    case 'session-new':
      return 1
    case 'session':
    case 'card':
    case 'card-lookup':
      return 2
  }
}

export function routeKey (route: Route): string {
  switch (route.name) {
    case 'home':
      return 'home'
    case 'install':
      return 'install'
    case 'proficiency':
      return 'proficiency'
    case 'session-new':
      return `session-new:${route.categoryId}`
    case 'session':
      return `session:${route.categoryId}:${serializeDifficulties(route.difficulties)}`
    case 'card':
      return `card:${route.mode}:${route.wordId}`
    case 'card-lookup':
      return `card-lookup:${route.mode}:${route.chinese}`
  }
}

export function screenMotion (
  from: Route | null,
  to: Route,
  options: { skipStack?: boolean } = {}
): ScreenMotionKind {
  if (options.skipStack || from === null) return 'none'
  if (
    from.name === 'session' ||
    to.name === 'session' ||
    from.name === 'card' ||
    to.name === 'card' ||
    from.name === 'card-lookup' ||
    to.name === 'card-lookup'
  ) {
    return 'fade'
  }
  const fromDepth = routeDepth(from)
  const toDepth = routeDepth(to)
  if (toDepth > fromDepth) return 'forward'
  if (toDepth < fromDepth) return 'back'
  return 'none'
}
