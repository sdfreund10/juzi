import type { Category } from './api'
import { navigate } from './routes'
import { useCategories } from './useCategories'

function wordCount(category: Category): number {
  return (
    category.beginner_count +
    category.intermediate_count +
    category.advanced_count
  )
}

export function Decks() {
  const { categories, error } = useCategories()

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
        <section class="list" aria-label="Decks">
          {categories.map((category) => {
            const total = wordCount(category)
            return (
              <button
                key={category.id}
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
          })}
        </section>
      ) : null}
    </>
  )
}
