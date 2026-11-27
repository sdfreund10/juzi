import { useState } from 'preact/hooks'
import type { Category } from './api'
import { useAuth } from './auth'
import { Brand } from './brand'
import {
  decksMatchingName,
  pinnedDecks,
  readPinnedDeckIds,
  recentlyPracticedDecks,
  togglePinnedDeckId,
  writePinnedDeckIds
} from './deckList'
import { LearnerScoreStrip } from './learnerScoreStrip'
import { cachedCategoryIds } from './offlineStore'
import { navigate } from './routes'
import { useCategories } from './useCategories'
import { useLearnerScore } from './useLearnerScore'

function DeckRow ({
  category,
  pinned,
  available,
  onTogglePin
}: {
  category: Category
  pinned: boolean
  available: boolean
  onTogglePin: (id: number) => void
}) {
  return (
    <div class={`row-group${available ? '' : ' unavailable'}`}>
      <button
        type='button'
        class='row'
        disabled={!available}
        onClick={() => {
          if (!available) return
          navigate({ name: 'session-new', categoryId: category.id })
        }}
      >
        <span class='g'>
          <b>{category.name}</b>
        </span>
      </button>
      <button
        type='button'
        class={`pin-btn${pinned ? ' pinned' : ''}`}
        aria-label={pinned ? `Unpin ${category.name}` : `Pin ${category.name}`}
        aria-pressed={pinned}
        onClick={() => onTogglePin(category.id)}
      >
        <svg
          viewBox='0 0 24 24'
          fill='none'
          stroke='currentColor'
          stroke-width='1.75'
          stroke-linecap='round'
          stroke-linejoin='round'
          aria-hidden='true'
        >
          <path d='M9 3h6l-1 7 4 4v2H6v-2l4-4-1-7Z' />
          <path d='M12 16v5' />
        </svg>
      </button>
    </div>
  )
}

function CustomDecksSection ({
  categories,
  showBuild,
  pinnedIds,
  availableIds,
  onTogglePin
}: {
  categories: Category[]
  showBuild: boolean
  pinnedIds: number[]
  availableIds: Set<number> | null
  onTogglePin: (id: number) => void
}) {
  if (categories.length === 0 && !showBuild) return null
  return (
    <details class='list deck-section custom-decks' open>
      <summary class='list-heading'>
        <h2>Custom decks</h2>
        <svg
          class='section-chevron'
          viewBox='0 0 24 24'
          fill='none'
          stroke='currentColor'
          stroke-width='2'
          stroke-linecap='round'
          stroke-linejoin='round'
          aria-hidden='true'
        >
          <path d='m9 6 6 6-6 6' />
        </svg>
      </summary>
      {categories.map((category) => (
        <DeckRow
          key={category.id}
          category={category}
          pinned={pinnedIds.includes(category.id)}
          available={availableIds === null || availableIds.has(category.id)}
          onTogglePin={onTogglePin}
        />
      ))}
      {showBuild && (
        <button
          type='button'
          class='text-btn build-deck'
          onClick={() => navigate({ name: 'deck-new' })}
        >
          + Build new deck
        </button>
      )}
    </details>
  )
}

function DeckSection ({
  label,
  categories,
  pinnedIds,
  availableIds,
  onTogglePin
}: {
  label: string
  categories: Category[]
  pinnedIds: number[]
  availableIds: Set<number> | null
  onTogglePin: (id: number) => void
}) {
  if (categories.length === 0) return null
  return (
    <details class='list deck-section' open>
      <summary class='list-heading'>
        <h2>{label}</h2>
        <svg
          class='section-chevron'
          viewBox='0 0 24 24'
          fill='none'
          stroke='currentColor'
          stroke-width='2'
          stroke-linecap='round'
          stroke-linejoin='round'
          aria-hidden='true'
        >
          <path d='m9 6 6 6-6 6' />
        </svg>
      </summary>
      {categories.map((category) => (
        <DeckRow
          key={category.id}
          category={category}
          pinned={pinnedIds.includes(category.id)}
          available={availableIds === null || availableIds.has(category.id)}
          onTogglePin={onTogglePin}
        />
      ))}
    </details>
  )
}

export function Decks () {
  const { offline, retryConnection } = useAuth()
  const { categories, error } = useCategories()
  const { snapshot } = useLearnerScore()
  const [query, setQuery] = useState('')
  const [retrying, setRetrying] = useState(false)
  const [pinnedIds, setPinnedIds] = useState<number[]>(() =>
    readPinnedDeckIds()
  )

  async function onRetryConnection () {
    if (retrying) return
    setRetrying(true)
    try {
      await retryConnection()
    } finally {
      setRetrying(false)
    }
  }

  function onTogglePin (id: number) {
    setPinnedIds((current) => {
      const next = togglePinnedDeckId(current, id)
      writePinnedDeckIds(next)
      return next
    })
  }

  const searching = query.trim().length > 0
  const named =
    categories === null ? null : decksMatchingName(categories, query)
  const publicNamed =
    named === null
      ? null
      : named.filter((category) => category.public !== false)
  const customNamed =
    named === null
      ? []
      : named.filter((category) => category.public === false)
  const pinned =
    publicNamed === null || searching
      ? []
      : pinnedDecks(publicNamed, pinnedIds)
  const recent =
    publicNamed === null || searching
      ? []
      : recentlyPracticedDecks(publicNamed).filter(
        (category) => !pinnedIds.includes(category.id)
      )
  const availableIds = offline ? cachedCategoryIds() : null
  const customSection = (
    <CustomDecksSection
      categories={customNamed}
      showBuild={!offline}
      pinnedIds={pinnedIds}
      availableIds={availableIds}
      onTogglePin={onTogglePin}
    />
  )

  return (
    <>
      <Brand
        end={snapshot ? <LearnerScoreStrip snapshot={snapshot} /> : null}
      />
      <h1 class='title'>Choose a deck</h1>

      {offline && (
        <p class='subtitle offline-status' role='status'>
          Offline · progress not saved.{' '}
          <button
            type='button'
            class='offline-retry'
            disabled={retrying}
            onClick={() => {
              onRetryConnection().catch(() => {})
            }}
          >
            {retrying ? 'Reconnecting…' : 'Reconnect?'}
          </button>
        </p>
      )}

      {error && (
        <p class='error' role='alert' aria-live='polite'>
          {error}
        </p>
      )}

      {categories === null && !error
        ? (
          <p class='subtitle'>Loading decks…</p>
          )
        : categories !== null && categories.length === 0
          ? (
            <>
              <section class='panel'>
                <p>No decks yet. Seed vocabulary to get started.</p>
              </section>
              {customSection}
            </>
            )
          : categories !== null
            ? (
              <>
                <label class='deck-search'>
                  <svg
                    class='deck-search-icon'
                    viewBox='0 0 24 24'
                    fill='none'
                    stroke='currentColor'
                    stroke-width='2'
                    stroke-linecap='round'
                    aria-hidden='true'
                  >
                    <circle cx='10.5' cy='10.5' r='6.5' />
                    <path d='m16 16 4 4' />
                  </svg>
                  <input
                    type='search'
                    name='deck-search'
                    aria-label='Search decks'
                    placeholder='Search decks'
                    value={query}
                    onInput={(e) =>
                      setQuery((e.target as HTMLInputElement).value)}
                  />
                </label>

                {searching
                  ? (
                    <>
                      {publicNamed !== null &&
                      publicNamed.length === 0 &&
                      customNamed.length === 0
                        ? <p class='subtitle'>No decks match.</p>
                        : publicNamed !== null && publicNamed.length > 0
                          ? (
                            <section class='list' aria-label='Decks'>
                              {publicNamed.map((category) => (
                                <DeckRow
                                  key={category.id}
                                  category={category}
                                  pinned={pinnedIds.includes(category.id)}
                                  available={
                                    availableIds === null ||
                                    availableIds.has(category.id)
                                  }
                                  onTogglePin={onTogglePin}
                                />
                              ))}
                            </section>
                            )
                          : null}
                      {customSection}
                    </>
                    )
                  : (
                    <>
                      <DeckSection
                        label='Pinned'
                        categories={pinned}
                        pinnedIds={pinnedIds}
                        availableIds={availableIds}
                        onTogglePin={onTogglePin}
                      />
                      <DeckSection
                        label='Recent'
                        categories={recent}
                        pinnedIds={pinnedIds}
                        availableIds={availableIds}
                        onTogglePin={onTogglePin}
                      />
                      {customSection}
                      <DeckSection
                        label={
                          pinned.length > 0 || recent.length > 0
                            ? 'All decks'
                            : 'Decks'
                        }
                        categories={publicNamed ?? []}
                        pinnedIds={pinnedIds}
                        availableIds={availableIds}
                        onTogglePin={onTogglePin}
                      />
                    </>
                    )}
              </>
              )
            : null}
    </>
  )
}
