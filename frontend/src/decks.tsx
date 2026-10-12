import { useState } from 'preact/hooks'
import type { Category } from './api'
import {
  decksMatchingName,
  pinnedDecks,
  readPinnedDeckIds,
  recentlyPracticedDecks,
  togglePinnedDeckId,
  writePinnedDeckIds,
} from './deckList'
import { navigate } from './routes'
import { useCategories } from './useCategories'

function wordCount(category: Category): number {
  return (
    category.beginner_count +
    category.intermediate_count +
    category.advanced_count
  )
}

function DeckRow({
  category,
  pinned,
  onTogglePin,
}: {
  category: Category
  pinned: boolean
  onTogglePin: (id: number) => void
}) {
  const total = wordCount(category)
  return (
    <div class="row-group">
      <button
        type="button"
        class={`pin-btn${pinned ? ' pinned' : ''}`}
        aria-label={pinned ? `Unpin ${category.name}` : `Pin ${category.name}`}
        aria-pressed={pinned}
        onClick={() => onTogglePin(category.id)}
      >
        {pinned ? 'Pinned' : 'Pin'}
      </button>
      <button
        type="button"
        class="row"
        onClick={() =>
          navigate({ name: 'session-new', categoryId: category.id })
        }
      >
        <span class="g">
          <b>{category.name}</b>
          <span class="s">
            {total === 1 ? '1 word' : `${total} words`}
          </span>
        </span>
      </button>
    </div>
  )
}

function DeckSection({
  label,
  categories,
  pinnedIds,
  onTogglePin,
}: {
  label: string
  categories: Category[]
  pinnedIds: number[]
  onTogglePin: (id: number) => void
}) {
  if (categories.length === 0) return null
  return (
    <section class="list" aria-label={label}>
      <h2 class="list-heading">{label}</h2>
      {categories.map((category) => (
        <DeckRow
          key={category.id}
          category={category}
          pinned={pinnedIds.includes(category.id)}
          onTogglePin={onTogglePin}
        />
      ))}
    </section>
  )
}

export function Decks() {
  const { categories, error } = useCategories()
  const [query, setQuery] = useState('')
  const [pinnedIds, setPinnedIds] = useState<number[]>(() =>
    readPinnedDeckIds(),
  )

  function onTogglePin(id: number) {
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
          (category) => !pinnedIds.includes(category.id),
        )

  return (
    <>
      <h1 class="title">Choose a deck</h1>

      {error && (
        <p class="error" role="alert" aria-live="polite">
          {error}
        </p>
      )}

      {categories === null && !error ? (
        <p class="subtitle">Loading decks…</p>
      ) : categories !== null && categories.length === 0 ? (
        <section class="panel">
          <p>No decks yet. Seed vocabulary to get started.</p>
        </section>
      ) : categories !== null ? (
        <>
          <label class="deck-search">
            <span class="deck-search-label">Search</span>
            <input
              type="search"
              name="deck-search"
              placeholder="Search decks"
              value={query}
              onInput={(e) =>
                setQuery((e.target as HTMLInputElement).value)
              }
            />
          </label>

          {visible !== null && visible.length === 0 ? (
            <p class="subtitle">
              {searching ? 'No decks match.' : 'No decks yet.'}
            </p>
          ) : searching ? (
            <section class="list" aria-label="Decks">
              {visible?.map((category) => (
                <DeckRow
                  key={category.id}
                  category={category}
                  pinned={pinnedIds.includes(category.id)}
                  onTogglePin={onTogglePin}
                />
              ))}
            </section>
          ) : (
            <>
              <DeckSection
                label="Pinned"
                categories={pinned}
                pinnedIds={pinnedIds}
                onTogglePin={onTogglePin}
              />
              <DeckSection
                label="Recent"
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
      ) : null}
    </>
  )
}
