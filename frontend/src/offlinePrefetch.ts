import {
  createSession,
  type Category,
  type Difficulty,
  type ProficiencyLevel
} from './api'
import {
  pinnedDecks,
  readPinnedDeckIds,
  recentlyPracticedDecks
} from './deckList'
import {
  OFFLINE_DECK_LIMIT,
  cacheOfflineDeck,
  cachedCategoryIds,
  offlineDeckCount
} from './offlineStore'

let learnerSessionInFlight = 0
let fillGeneration = 0
let fillRunning = false
let fillQueued: {
  categories: Category[]
  proficiency: ProficiencyLevel
} | null = null

export function beginLearnerSessionBuild (): void {
  learnerSessionInFlight += 1
}

export function endLearnerSessionBuild (): void {
  learnerSessionInFlight = Math.max(0, learnerSessionInFlight - 1)
  if (learnerSessionInFlight === 0 && fillQueued && !fillRunning) {
    const next = fillQueued
    fillQueued = null
    startOfflinePrefetch(next.categories, next.proficiency)
  }
}

export function stopOfflinePrefetch (): void {
  fillGeneration += 1
  fillQueued = null
  fillRunning = false
}

export function prefetchCandidateIds (categories: Category[]): number[] {
  const pinnedIds = readPinnedDeckIds()
  const pinned = pinnedDecks(categories, pinnedIds)
  const recent = recentlyPracticedDecks(categories).filter(
    (category) => !pinnedIds.includes(category.id)
  )
  const used = new Set([...pinned, ...recent].map((category) => category.id))
  const rest = categories.filter((category) => !used.has(category.id))
  return [...pinned, ...recent, ...rest].map((category) => category.id)
}

async function runFill (
  generation: number,
  categories: Category[],
  proficiency: Difficulty
): Promise<void> {
  const candidates = prefetchCandidateIds(categories)
  for (const categoryId of candidates) {
    if (generation !== fillGeneration) return
    if (offlineDeckCount() >= OFFLINE_DECK_LIMIT) return
    if (cachedCategoryIds().has(categoryId)) continue
    if (learnerSessionInFlight > 0) {
      fillQueued = { categories, proficiency }
      return
    }

    try {
      const session = await createSession(categoryId, [proficiency])
      if (generation !== fillGeneration) return
      if (session.cards.length === 0) continue
      if (offlineDeckCount() >= OFFLINE_DECK_LIMIT) return
      if (cachedCategoryIds().has(categoryId)) continue
      cacheOfflineDeck(session, 'prefetch')
    } catch {
      // Prefetch failures stay silent.
    }
  }
}

/** Fill the offline store up to ten decks. Safe to call repeatedly; non-blocking. */
export function startOfflinePrefetch (
  categories: Category[],
  proficiency: ProficiencyLevel | null
): void {
  if (!proficiency) return
  if (offlineDeckCount() >= OFFLINE_DECK_LIMIT) return

  if (learnerSessionInFlight > 0) {
    fillQueued = { categories, proficiency }
    return
  }

  fillGeneration += 1
  const generation = fillGeneration
  fillRunning = true
  runFill(generation, categories, proficiency)
    .catch(() => {})
    .finally(() => {
      if (generation === fillGeneration) {
        fillRunning = false
        if (fillQueued && learnerSessionInFlight === 0) {
          const next = fillQueued
          fillQueued = null
          startOfflinePrefetch(next.categories, next.proficiency)
        }
      }
    })
}
