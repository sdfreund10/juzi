import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'
import { ApiError, buildDeck, type DeckSize } from './api'
import { useAuth } from './auth'
import { Brand } from './brand'
import { navigate } from './routes'

const SIZES: DeckSize[] = [20, 40, 60]
const NO_MATCH = 'No matching words.'
const UNAVAILABLE = 'Could not build a deck. Try again.'

function fitPrompt (el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  const next = el.scrollHeight
  if (next > 0) el.style.height = `${next}px`
}

export function DeckNew () {
  const { clearUser } = useAuth()
  const [prompt, setPrompt] = useState('')
  const [size, setSize] = useState<DeckSize>(40)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const alive = useRef(true)
  const promptRef = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const el = promptRef.current
    if (el) fitPrompt(el)
  }, [prompt])

  useEffect(() => {
    return () => {
      alive.current = false
    }
  }, [])

  async function onSubmit (event: Event) {
    event.preventDefault()
    const trimmed = prompt.trim()
    if (!trimmed || submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const deck = await buildDeck(trimmed, size)
      if (!alive.current) return
      if (!Number.isInteger(deck.id) || deck.id < 1) {
        setError(UNAVAILABLE)
        return
      }
      navigate({ name: 'session-new', categoryId: deck.id }, { replace: true })
    } catch (err) {
      if (!alive.current) return
      if (err instanceof ApiError && err.status === 401) {
        clearUser()
        return
      }
      setError(
        err instanceof ApiError && err.message === NO_MATCH ? NO_MATCH : UNAVAILABLE
      )
    } finally {
      if (alive.current) setSubmitting(false)
    }
  }

  return (
    <>
      <Brand />
      <div class='title-bar'>
        <h1 class='title'>New deck</h1>
        <button
          type='button'
          class='text-btn'
          onClick={() => navigate({ name: 'home' })}
        >
          Back
        </button>
      </div>

      <form class='deck-form' onSubmit={(event) => { onSubmit(event).catch(() => {}) }}>
        <label class='deck-prompt'>
          <span>What do you want to prepare for?</span>
          <textarea
            ref={promptRef}
            name='prompt'
            rows={1}
            required
            value={prompt}
            disabled={submitting}
            onInput={(e) => setPrompt((e.target as HTMLTextAreaElement).value)}
          />
        </label>

        <fieldset class='deck-size' disabled={submitting}>
          <legend>Size</legend>
          <div class='deck-size-options'>
            {SIZES.map((option) => (
              <label key={option} class={option === size ? 'selected' : ''}>
                <input
                  type='radio'
                  name='size'
                  value={String(option)}
                  checked={option === size}
                  onChange={() => setSize(option)}
                />
                {option}
              </label>
            ))}
          </div>
        </fieldset>

        {submitting && (
          <p class='deck-status' role='status'>
            Choosing words…
          </p>
        )}
        {error && (
          <p class='error' role='alert' aria-live='polite'>
            {error}
          </p>
        )}

        <div class='picker-actions deck-actions'>
          <button type='submit' class='cta' disabled={submitting}>
            Build
          </button>
          <button
            type='button'
            class='text-btn'
            onClick={() => navigate({ name: 'home' })}
          >
            Cancel
          </button>
        </div>
      </form>
    </>
  )
}
