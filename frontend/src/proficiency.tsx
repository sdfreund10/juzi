import { useState } from 'preact/hooks'
import { ApiError, setProficiencyLevel, type ProficiencyLevel } from './api'
import { useAuth } from './auth'
import { Brand } from './brand'
import { navigate } from './routes'

const OPTIONS: { id: ProficiencyLevel; label: string; detail: string }[] = [
  { id: 'novice', label: 'Novice', detail: 'Start with pinyin helper on all cards.' },
  { id: 'intermediate', label: 'Intermediate', detail: 'Adds English-to-Chinese cards for beginner words.' },
  { id: 'advanced', label: 'Advanced', detail: 'Adds English-to-Chinese cards for all words and character-only prompts for beginner words.' },
  { id: 'expert', label: 'Expert', detail: 'All card types for all words.' }
]

const FIELD_NAME = 'proficiency_level'

export function ProficiencyStep () {
  const { user, setUser, clearUser } = useAuth()
  const current = user?.proficiency_level ?? null
  const isEdit = current !== null

  const [selected, setSelected] = useState<ProficiencyLevel | null>(current)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const canConfirm =
    selected !== null && (!isEdit || selected !== current) && !submitting

  async function confirm () {
    if (!canConfirm || selected === null) return
    setError(null)
    setSubmitting(true)
    try {
      const nextUser = await setProficiencyLevel(selected)
      setUser(nextUser)
      navigate({ name: 'home' }, { replace: !isEdit })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearUser()
        return
      }
      if (err instanceof ApiError && err.status === 400) {
        setError(err.message)
      } else {
        setError('Could not save your level. Try again.')
      }
      setSubmitting(false)
    }
  }

  function onRadioChange (level: ProficiencyLevel) {
    if (submitting) return
    setError(null)
    setSelected(level)
  }

  return (
    <>
      <Brand />
      <div class='title-bar'>
        <h1 class='title' id='proficiency-title'>
          {isEdit ? 'Change proficiency level' : 'Select your proficiency level'}
        </h1>
        {isEdit && (
          <button
            type='button'
            class='text-btn'
            onClick={() => navigate({ name: 'home' })}
            disabled={submitting}
          >
            Home
          </button>
        )}
      </div>
      <p class='lede'>Selecting a higher level will unlock harder study modes.</p>

      <fieldset
        class='proficiency-field'
        disabled={submitting}
        aria-labelledby='proficiency-title'
      >
        <legend class='proficiency-legend'>Proficiency level</legend>
        {OPTIONS.map((opt) => {
          const isSelected = selected === opt.id
          return (
            <label
              key={opt.id}
              class={`proficiency-option${isSelected ? ' selected' : ''}`}
            >
              <input
                type='radio'
                name={FIELD_NAME}
                value={opt.id}
                checked={isSelected}
                onChange={() => onRadioChange(opt.id)}
              />
              <span class='g'>
                <b>{opt.label}</b>
                <span class='s'>{opt.detail}</span>
              </span>
            </label>
          )
        })}
      </fieldset>

      <div class='picker-actions'>
        <button
          type='button'
          class='cta'
          disabled={!canConfirm}
          onClick={() => { confirm().catch(() => {}) }}
        >
          {submitting ? 'Saving…' : isEdit ? 'Save changes' : 'Confirm'}
        </button>
      </div>

      {error && (
        <p class='error' role='alert' aria-live='polite'>
          {error}
        </p>
      )}
    </>
  )
}
