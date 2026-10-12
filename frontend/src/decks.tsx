import { useState } from 'preact/hooks'
import type { Category } from './api'
import { decksMatchingName, recentlyPracticedDecks } from './deckList'
import { navigate } from './routes'
import { useCategories } from './useCategories'

function wordCount(category: Category): number {
  return (
    category.beginner_count +
    category.intermediate_count +
    category.advanced_count
  )
}

function DeckRow({ category }: { category: Category }) {
  const total = wordCount(category)
  return (
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
  )
}

function DeckSection({
  label,
  categories,
}: {
  label: string
  categories: Category[]
}) {
  if (categories.length === 0) return null
  return (
    <section class="list" aria-label={label}>
      <h2 class="list-heading">{label}</h2>
      {categories.map((category) => (
        <DeckRow key={category.id} category={category} />
      ))}
    </section>
  )
}

export function Decks() {
  const { categories, error } = useCategories()
  const [query, setQuery] = useState('')

  const searching = query.trim().length > 0
  const visible =
    categories === null ? null : decksMatchingName(categories, query)
  const recent =
    visible === null || searching
      ? []
      : recentlyPracticedDecks(visible)

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
                <DeckRow key={category.id} category={category} />
              ))}
            </section>
          ) : (
            <>
              <DeckSection label="Recent" categories={recent} />
              <DeckSection
                label={recent.length > 0 ? 'All decks' : 'Decks'}
                categories={visible ?? []}
              />
            </>
          )}
        </>
      ) : null}
    </>
  )
}
