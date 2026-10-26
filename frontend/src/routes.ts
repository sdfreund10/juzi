import type { Difficulty } from './api'

export const DIFFICULTY_ORDER: Difficulty[] = [
  'novice',
  'intermediate',
  'advanced',
  'expert'
]

const DIFFICULTY_SET = new Set<string>(DIFFICULTY_ORDER)

export const STUDY_MODES = ['pinyin_to_en', 'en_to_zh', 'zh_to_en'] as const

export type StudyMode = (typeof STUDY_MODES)[number]

const STUDY_MODE_SET = new Set<string>(STUDY_MODES)

export const DEFAULT_STUDY_MODE: StudyMode = 'pinyin_to_en'

export type Route =
  | { name: 'home' }
  | { name: 'install' }
  | { name: 'proficiency' }
  | { name: 'session-new'; categoryId: number }
  | { name: 'session'; categoryId: number; difficulties: Difficulty[] }
  | { name: 'card'; mode: StudyMode; wordId: number }
  | { name: 'card-lookup'; mode: StudyMode; chinese: string }

export function serializeDifficulties (difficulties: Difficulty[]): string {
  return DIFFICULTY_ORDER.filter((id) => difficulties.includes(id)).join('-')
}

export function parseDifficulties (slug: string): Difficulty[] | null {
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

function parseStudyMode (value: string | null): StudyMode | null {
  if (value === null || value === '') return DEFAULT_STUDY_MODE
  if (!STUDY_MODE_SET.has(value)) return null
  return value as StudyMode
}

function modeQuery (mode: StudyMode): string {
  return `?mode=${mode}`
}

function decodePathname (pathname: string): string {
  try {
    return decodeURIComponent(pathname)
  } catch {
    return pathname
  }
}

function parseCardPath (path: string, search: string): Route | null {
  const match = path.match(/^\/cards\/([^/]+)$/)
  if (!match) return null

  const mode = parseStudyMode(new URLSearchParams(search).get('mode'))
  if (!mode) return null

  const key = match[1]
  if (/^\d+$/.test(key)) {
    const wordId = Number(key)
    if (!Number.isInteger(wordId) || wordId < 1) return null
    return { name: 'card', mode, wordId }
  }

  return { name: 'card-lookup', mode, chinese: key }
}

export function parsePath (pathname: string, search = ''): Route {
  const path = decodePathname(pathname).replace(/\/+$/, '') || '/'
  if (path === '/') return { name: 'home' }
  if (path === '/install') return { name: 'install' }
  if (path === '/proficiency') return { name: 'proficiency' }

  const card = parseCardPath(path, search)
  if (card) return card

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

export function pathFor (route: Route): string {
  switch (route.name) {
    case 'home':
      return '/'
    case 'install':
      return '/install'
    case 'proficiency':
      return '/proficiency'
    case 'session-new':
      return `/category/${route.categoryId}/sessions/new`
    case 'session':
      return `/category/${route.categoryId}/sessions/${serializeDifficulties(route.difficulties)}`
    case 'card':
      return `/cards/${route.wordId}${modeQuery(route.mode)}`
    case 'card-lookup':
      return `/cards/${route.chinese}${modeQuery(route.mode)}`
  }
}

function currentLocation (): string {
  return `${window.location.pathname}${window.location.search}`
}

let pendingReplaceNavigation = false

export function consumePendingReplaceNavigation (): boolean {
  const value = pendingReplaceNavigation
  pendingReplaceNavigation = false
  return value
}

export function navigate (route: Route, options: { replace?: boolean } = {}): void {
  const next = pathFor(route)
  if (next === currentLocation()) return
  if (options.replace) {
    pendingReplaceNavigation = true
    window.history.replaceState(null, '', next)
  } else {
    window.history.pushState(null, '', next)
  }
  window.dispatchEvent(new PopStateEvent('popstate'))
}
