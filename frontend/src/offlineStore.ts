import type { AuthUser, Category, Difficulty, StudySession } from './api'
import { serializeDifficulties } from './routes'

export const OFFLINE_USER_KEY = 'juzi.offlineUser'
export const OFFLINE_CATEGORIES_KEY = 'juzi.offlineCategories'
export const OFFLINE_DECKS_KEY = 'juzi.offlineDecks'

export const OFFLINE_DECK_LIMIT = 10

export type OfflineCachedUser = {
  email: string
  proficiency_level: AuthUser['proficiency_level']
}

export type OfflineDeckSource = 'studied' | 'prefetch'

export type OfflineDeckEntry = {
  categoryId: number
  difficulties: Difficulty[]
  session: StudySession
  source: OfflineDeckSource
  cachedAt: string
}

function isQuotaExceeded (err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const name = 'name' in err ? String(err.name) : ''
  return name === 'QuotaExceededError' || name === 'NS_ERROR_DOM_QUOTA_REACHED'
}

function readJson<T> (key: string): T | null {
  const raw = localStorage.getItem(key)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function writeJson (key: string, value: unknown): void {
  localStorage.setItem(key, JSON.stringify(value))
}

export function readOfflineUser (): OfflineCachedUser | null {
  const value = readJson<OfflineCachedUser>(OFFLINE_USER_KEY)
  if (!value || typeof value.email !== 'string') return null
  return value
}

export function writeOfflineUser (user: OfflineCachedUser): void {
  writeJson(OFFLINE_USER_KEY, user)
}

export function readOfflineCategories (): Category[] | null {
  const value = readJson<Category[]>(OFFLINE_CATEGORIES_KEY)
  return Array.isArray(value) ? value : null
}

function categoryFromDeck (entry: OfflineDeckEntry): Category {
  const { id, name } = entry.session.category
  return {
    id,
    name,
    novice_count: 0,
    intermediate_count: 0,
    advanced_count: 0,
    expert_count: 0,
    last_practiced_at: null
  }
}

/** Stored category list, or one row per cached category when that list is missing. */
export function categoriesAvailableOffline (): Category[] | null {
  const stored = readOfflineCategories()
  if (stored) return stored

  const byId = new Map<number, Category>()
  for (const entry of readOfflineDecks()) {
    const category = categoryFromDeck(entry)
    if (!byId.has(category.id)) byId.set(category.id, category)
  }
  return byId.size > 0 ? [...byId.values()] : null
}

export function writeOfflineCategories (categories: Category[]): void {
  writeJson(OFFLINE_CATEGORIES_KEY, categories)
}

export function readOfflineDecks (): OfflineDeckEntry[] {
  const value = readJson<OfflineDeckEntry[]>(OFFLINE_DECKS_KEY)
  return Array.isArray(value) ? value : []
}

function writeOfflineDecks (entries: OfflineDeckEntry[]): void {
  writeJson(OFFLINE_DECKS_KEY, entries)
}

export function clearOfflineStore (): void {
  localStorage.removeItem(OFFLINE_USER_KEY)
  localStorage.removeItem(OFFLINE_CATEGORIES_KEY)
  localStorage.removeItem(OFFLINE_DECKS_KEY)
}

/** Drop the whole offline cache when a different learner signs in. */
export function syncOfflineUser (user: OfflineCachedUser): void {
  const current = readOfflineUser()
  if (current && current.email !== user.email) {
    clearOfflineStore()
  }
  writeOfflineUser(user)
}

export function offlineDeckKey (
  categoryId: number,
  difficulties: Difficulty[]
): string {
  return `${categoryId}:${serializeDifficulties(difficulties)}`
}

function dropOneDeck (entries: OfflineDeckEntry[]): OfflineDeckEntry[] {
  if (entries.length === 0) return entries
  const prefetchIndex = [...entries]
    .map((entry, index) => ({ entry, index }))
    .filter(({ entry }) => entry.source === 'prefetch')
    .sort((a, b) => a.entry.cachedAt.localeCompare(b.entry.cachedAt))[0]?.index
  if (prefetchIndex !== undefined) {
    return entries.filter((_, index) => index !== prefetchIndex)
  }
  const oldestIndex = [...entries]
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => a.entry.cachedAt.localeCompare(b.entry.cachedAt))[0]?.index
  if (oldestIndex === undefined) return entries.slice(0, -1)
  return entries.filter((_, index) => index !== oldestIndex)
}

function persistDecks (entries: OfflineDeckEntry[]): void {
  let next = entries
  while (next.length > OFFLINE_DECK_LIMIT) {
    next = dropOneDeck(next)
  }
  try {
    writeOfflineDecks(next)
  } catch (err) {
    if (!isQuotaExceeded(err)) throw err
    const reduced = dropOneDeck(next)
    if (reduced.length === next.length) throw err
    writeOfflineDecks(reduced)
  }
}

export function cacheOfflineDeck (
  session: StudySession,
  source: OfflineDeckSource
): void {
  if (session.cards.length === 0) return

  const categoryId = session.category.id
  const difficulties = session.difficulties
  const entry: OfflineDeckEntry = {
    categoryId,
    difficulties,
    session,
    source,
    cachedAt: new Date().toISOString()
  }

  const withoutSameDeck = readOfflineDecks().filter(
    (row) => row.categoryId !== categoryId
  )
  persistDecks([entry, ...withoutSameDeck])
}

export function findOfflineDeck (
  categoryId: number,
  difficulties?: Difficulty[]
): OfflineDeckEntry | null {
  const entries = readOfflineDecks()
  if (difficulties) {
    const key = offlineDeckKey(categoryId, difficulties)
    return (
      entries.find(
        (entry) => offlineDeckKey(entry.categoryId, entry.difficulties) === key
      ) ?? null
    )
  }
  return entries.find((entry) => entry.categoryId === categoryId) ?? null
}

export function hasOfflineDeck (categoryId: number): boolean {
  return findOfflineDeck(categoryId) !== null
}

export function offlineDeckCount (): number {
  return readOfflineDecks().length
}

export function cachedCategoryIds (): Set<number> {
  return new Set(readOfflineDecks().map((entry) => entry.categoryId))
}
