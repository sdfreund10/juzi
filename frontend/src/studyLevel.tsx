import { useState } from 'preact/hooks'
import { ApiError, setStudyLevel, type StudyLevel } from './api'
import { Brand } from './brand'
import { useAuth } from './auth'

const OPTIONS: { id: StudyLevel; label: string; detail: string }[] = [
  {
    id: 'novice',
    label: 'Novice',
    detail: 'Start with pinyin to English.',
  },
  {
    id: 'intermediate',
    label: 'Intermediate',
    detail: 'English to Chinese opens for HSK 1–3.',
  },
  {
    id: 'advanced',
    label: 'Advanced',
    detail: 'Character cards for HSK 1–3; English to Chinese for all.',
  },
  {
    id: 'superior',
    label: 'Superior',
    detail: 'All three directions for every word.',
  },
]

export function StudyLevelStep() {
  const { setUser } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState<StudyLevel | null>(null)

  async function choose(level: StudyLevel) {
    if (submitting) return
    setError(null)
    setSubmitting(level)
    try {
      const user = await setStudyLevel(level)
      setUser(user)
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError(err.message)
      } else {
        setError('Could not save your level. Try again.')
      }
      setSubmitting(null)
    }
  }

  return (
    <>
      <Brand />
      <h1 class="title">How well do you read Chinese?</h1>
      <p class="lede">This sets which quiz directions open first.</p>

      <section class="difficulty-grid" aria-label="Study level">
        {OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            class="difficulty-option"
            disabled={submitting !== null}
            aria-busy={submitting === opt.id}
            onClick={() => void choose(opt.id)}
          >
            <span class="g">
              <b>{opt.label}</b>
              <span class="s">{opt.detail}</span>
            </span>
          </button>
        ))}
      </section>

      {error && (
        <p class="error" role="alert" aria-live="polite">
          {error}
        </p>
      )}
    </>
  )
}
