import { useEffect, useState } from 'preact/hooks'
import type { Category, Difficulty } from './api'
import { Brand } from './brand'
import { navigate } from './routes'
import { useCategory } from './useCategories'

const OPTIONS: { id: Difficulty; label: string; detail: string; countKey: keyof Category }[] = [
  { id: 'beginner', label: 'Beginner', detail: 'HSK 1–3', countKey: 'beginner_count' },
  {
    id: 'intermediate',
    label: 'Intermediate',
    detail: 'HSK 4–5',
    countKey: 'intermediate_count',
  },
  { id: 'advanced', label: 'Advanced', detail: 'HSK 6+', countKey: 'advanced_count' },
]

type DifficultyProps = {
  categoryId: number
}

export function DifficultyStep({ categoryId }: DifficultyProps) {
  const { category, ready, missing, error } = useCategory(categoryId)
  const [selected, setSelected] = useState<Set<Difficulty>>(() => new Set())

  useEffect(() => {
    if (missing) {
      navigate({ name: 'home' }, { replace: true })
    }
  }, [missing])

  if (error) {
    return (
      <>
        <Brand />
        <div class="title-bar">
          <h1 class="title">Difficulty</h1>
          <button
            type="button"
            class="text-btn"
            onClick={() => navigate({ name: 'home' })}
          >
            Back
          </button>
        </div>
        <p class="error" role="alert" aria-live="polite">
          {error}
        </p>
      </>
    )
  }

  if (!ready || !category) {
    return (
      <>
        <Brand />
        <p class="building-status">Loading…</p>
      </>
    )
  }

  const selectedCategory = category

  function toggle(id: Difficulty) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  function submit() {
    if (selected.size === 0) return
    navigate({
      name: 'session',
      categoryId: selectedCategory.id,
      difficulties: OPTIONS.map((opt) => opt.id).filter((id) => selected.has(id)),
    })
  }

  return (
    <>
      <Brand />
      <div class="title-bar">
        <h1 class="title">Select Level(s)</h1>
        <button
          type="button"
          class="text-btn"
          onClick={() => navigate({ name: 'home' })}
        >
          Back
        </button>
      </div>
      <p class="subtitle">{selectedCategory.name}</p>

      <section class="difficulty-grid" aria-label="Difficulty levels">
        {OPTIONS.map((opt) => {
          const isSelected = selected.has(opt.id)
          const count = selectedCategory[opt.countKey]
          return (
            <button
              key={opt.id}
              type="button"
              class={`difficulty-option${isSelected ? ' selected' : ''}`}
              aria-pressed={isSelected}
              onClick={() => toggle(opt.id)}
            >
              <span class="g">
                <b>{opt.label}</b>
                <span class="s">
                  {opt.detail}
                  {typeof count === 'number' ? ` · ${count} words` : ''}
                </span>
              </span>
            </button>
          )
        })}
      </section>

      <div class="picker-actions">
        <button
          type="button"
          class="cta"
          disabled={selected.size === 0}
          onClick={submit}
        >
          Start studying
        </button>
      </div>
    </>
  )
}
