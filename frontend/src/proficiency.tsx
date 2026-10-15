import { useState } from 'preact/hooks'
import { ApiError, setProficiencyLevel, type ProficiencyLevel } from './api'
import { useAuth } from './auth'
import { Brand } from './brand'
import { navigate } from './routes'

const OPTIONS: { id: ProficiencyLevel; label: string; detail: string }[] = [
  { id: 'novice', label: 'Novice', detail: 'HSK 1–2' },
  { id: 'intermediate', label: 'Intermediate', detail: 'HSK 3–4' },
  { id: 'advanced', label: 'Advanced', detail: 'HSK 5–6' },
  { id: 'expert', label: 'Expert', detail: 'HSK 7' },
]

export function ProficiencyStep() {
  const { user, setUser } = useAuth()
  const current = user?.proficiency_level ?? null
  const isEdit = current !== null

  const [selected, setSelected] = useState<ProficiencyLevel | null>(current)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const canConfirm =
    selected !== null && (!isEdit || selected !== current) && !submitting

  async function confirm() {
    if (!canConfirm || selected === null) return
    setError(null)
    setSubmitting(true)
    try {
      const nextUser = await setProficiencyLevel(selected)
      setUser(nextUser)
      navigate({ name: 'home' }, { replace: !isEdit })
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError(err.message)
      } else {
        setError('Could not save your level. Try again.')
      }
      setSubmitting(false)
    }
  }

  function select(level: ProficiencyLevel) {
    if (submitting) return
    setError(null)
    setSelected(level)
  }

  return (
    <>
      <Brand />
      <div class="title-bar">
        <h1 class="title">
          {isEdit ? 'Change proficiency level' : 'Select your proficiency level'}
        </h1>
        {isEdit && (
          <button
            type="button"
            class="text-btn"
            onClick={() => navigate({ name: 'home' })}
            disabled={submitting}
          >
            Back
          </button>
        )}
      </div>
      <p class="lede">Selecting a higher level will unlock harder study modes.</p>

      <section class="difficulty-grid" aria-label="Proficiency level">
        {OPTIONS.map((opt) => {
          const isSelected = selected === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              class={`difficulty-option${isSelected ? ' selected' : ''}`}
              disabled={submitting}
              aria-pressed={isSelected}
              onClick={() => select(opt.id)}
            >
              <span class="g">
                <b>{opt.label}</b>
                <span class="s">{opt.detail}</span>
              </span>
            </button>
          )
        })}
      </section>

      <div class="picker-actions">
        <button
          type="button"
          class="cta"
          disabled={!canConfirm}
          onClick={() => void confirm()}
        >
          {submitting ? 'Saving…' : isEdit ? 'Save changes' : 'Confirm'}
        </button>
      </div>

      {error && (
        <p class="error" role="alert" aria-live="polite">
          {error}
        </p>
      )}
    </>
  )
}
