import { useEffect, useState } from 'preact/hooks'
import {
  ApiError,
  createSession,
  type Difficulty,
  type StudySession,
} from './api'
import { navigate } from './routes'
import { useCategory } from './useCategories'

const MODE_LABELS: Record<string, string> = {
  pinyin_to_en: 'Pinyin to English',
  en_to_zh: 'English to Chinese',
  zh_to_en: 'Chinese to English',
}

type StudyProps = {
  categoryId: number
  difficulties: Difficulty[]
}

export function Study({ categoryId, difficulties }: StudyProps) {
  const { category, ready, missing } = useCategory(categoryId)
  const [session, setSession] = useState<StudySession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [empty, setEmpty] = useState(false)

  const difficultyKey = difficulties.join(',')

  useEffect(() => {
    if (missing) {
      navigate({ name: 'home' }, { replace: true })
    }
  }, [missing])

  useEffect(() => {
    if (!ready || missing) return

    let cancelled = false
    setSession(null)
    setError(null)
    setEmpty(false)

    async function build() {
      try {
        const next = await createSession(categoryId, difficulties)
        if (cancelled) return
        if (next.cards.length === 0) {
          setEmpty(true)
          return
        }
        setSession(next)
      } catch (err) {
        if (cancelled) return
        if (
          err instanceof ApiError &&
          err.status === 400 &&
          /no cards/i.test(err.message)
        ) {
          setEmpty(true)
          return
        }
        const message =
          err instanceof ApiError && err.message
            ? err.message
            : 'Could not build deck. Try again.'
        setError(message)
      }
    }

    void build()
    return () => {
      cancelled = true
    }
  }, [ready, missing, categoryId, difficultyKey])

  if (!ready || !category) {
    return <p class="building-status">Loading…</p>
  }

  if (empty) {
    return (
      <>
        <h1 class="title">No words due at this time!</h1>
        <div class="picker-actions">
          <button
            type="button"
            class="cta"
            onClick={() => navigate({ name: 'home' })}
          >
            Select a new category to study
          </button>
        </div>
      </>
    )
  }

  if (error) {
    return (
      <>
        <h1 class="title">Building deck</h1>
        <p class="subtitle">{category.name}</p>
        <p class="error" role="alert" aria-live="polite">
          {error}
        </p>
        <div class="picker-actions">
          <button
            type="button"
            class="cta"
            onClick={() =>
              navigate(
                { name: 'session-new', categoryId: category.id },
                { replace: true },
              )
            }
          >
            Back
          </button>
        </div>
      </>
    )
  }

  if (!session) {
    return (
      <>
        <h1 class="title">Building deck</h1>
        <p class="subtitle">{category.name}</p>
        <p class="building-status" aria-live="polite">
          Gathering cards…
        </p>
      </>
    )
  }

  const card = session.cards[0]
  const modeLabel = MODE_LABELS[card.mode] ?? card.mode

  return (
    <div class="study-shell">
      <div class="study-top">
        <div class="study-top-main">
          <span class="chip">{modeLabel}</span>
          <span class="muted">
            1 / {session.total}
          </span>
        </div>
        <button
          type="button"
          class="text-btn"
          onClick={() => navigate({ name: 'home' })}
        >
          Exit
        </button>
      </div>

      <p class="prompt zh pinyin">{card.prompt}</p>
      <p class="hint">Tap anywhere to reveal</p>
    </div>
  )
}
