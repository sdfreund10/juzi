import { useEffect, useState } from 'preact/hooks'
import { navigate } from './routes'

function prefersReducedMotion (): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

export function DeckComplete ({ scoreIncrease }: { scoreIncrease: number | null }) {
  const showIncrease = scoreIncrease != null && scoreIncrease > 0
  const floored = showIncrease ? Math.floor(scoreIncrease) : 0
  const [showMeta, setShowMeta] = useState(() => !showIncrease || prefersReducedMotion())

  useEffect(() => {
    if (!showIncrease || prefersReducedMotion()) {
      setShowMeta(true)
      return
    }
    setShowMeta(false)
  }, [showIncrease])

  return (
    <section class='caught-up deck-complete'>
      <h1 class='caught-up-title'>Deck complete</h1>
      {showIncrease
        ? (
          <div
            class='learner-score-increase'
            aria-live='polite'
            aria-label={`Learner score increased by ${floored}`}
          >
            <p
              class={`learner-score-increase-delta${prefersReducedMotion() ? ' instant' : ''}`}
              onAnimationEnd={() => setShowMeta(true)}
            >
              +{floored}
            </p>
            <p class={`learner-score-increase-label${showMeta ? ' visible' : ''}`}>
              Learner score increased
            </p>
          </div>
          )
        : null}
      <div class='picker-actions'>
        <button type='button' class='cta' onClick={() => navigate({ name: 'home' })}>
          Back to decks
        </button>
      </div>
    </section>
  )
}
