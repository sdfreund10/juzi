import { useState } from 'preact/hooks'
import type { Category } from './api'
import { Brand } from './brand'
import {
  decksMatchingName,
  pinnedDecks,
  readPinnedDeckIds,
  recentlyPracticedDecks,
  togglePinnedDeckId,
  writePinnedDeckIds
} from './deckList'
import { navigate } from './routes'
import { useCategories } from './useCategories'

function DeckRow ({
  category,
  pinned,
  onTogglePin
}: {
  category: Category
  pinned: boolean
  onTogglePin: (id: number) => void
}) {
  return (
    <div class='row-group'>
      <button
        type='button'
        class='row'
        onClick={() =>
          navigate({ name: 'session-new', categoryId: category.id })}
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

function DeckSection ({
  label,
  categories,
  pinnedIds,
  onTogglePin
}: {
  label: string
  categories: Category[]
  pinnedIds: number[]
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
          onTogglePin={onTogglePin}
        />
      ))}
    </details>
  )
}

export function Decks () {
  const { categories, error } = useCategories()
  const [query, setQuery] = useState('')
  const [pinnedIds, setPinnedIds] = useState<number[]>(() =>
    readPinnedDeckIds()
  )

  function onTogglePin (id: number) {
    setPinnedIds((current) => {
      const next = togglePinnedDeckId(current, id)
      writePinnedDeckIds(next)
      return next
    })
  }

  const searching = query.trim().length > 0
  const visible =
    categories === null ? null : decksMatchingName(categories, query)
  const pinned =
    visible === null || searching ? [] : pinnedDecks(visible, pinnedIds)
  const recent =
    visible === null || searching
      ? []
      : recentlyPracticedDecks(visible).filter(
        (category) => !pinnedIds.includes(category.id)
      )

  return (
    <>
      <Brand />
      <h1 class='title'>Choose a deck</h1>

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
            <section class='panel'>
              <p>No decks yet. Seed vocabulary to get started.</p>
            </section>
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

                {visible !== null && visible.length === 0
                  ? (
                    <p class='subtitle'>
                      {searching ? 'No decks match.' : 'No decks yet.'}
                    </p>
                    )
                  : searching
                    ? (
                      <section class='list' aria-label='Decks'>
                        {visible?.map((category) => (
                          <DeckRow
                            key={category.id}
                            category={category}
                            pinned={pinnedIds.includes(category.id)}
                            onTogglePin={onTogglePin}
                          />
                        ))}
                      </section>
                      )
                    : (
                      <>
                        <DeckSection
                          label='Pinned'
                          categories={pinned}
                          pinnedIds={pinnedIds}
                          onTogglePin={onTogglePin}
                        />
                        <DeckSection
                          label='Recent'
                          categories={recent}
                          pinnedIds={pinnedIds}
                          onTogglePin={onTogglePin}
                        />
                        <DeckSection
                          label={
                  pinned.length > 0 || recent.length > 0
                    ? 'All decks'
                    : 'Decks'
                }
                          categories={visible ?? []}
                          pinnedIds={pinnedIds}
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
