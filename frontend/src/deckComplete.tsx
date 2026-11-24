import { useEffect, useState } from 'preact/hooks'
import { navigate } from './routes'

function prefersReducedMotion (): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function TrendingUpIcon () {
  return (
    <svg
      class='learner-score-bump-icon'
      width='20'
      height='20'
      viewBox='0 0 24 24'
      fill='none'
      stroke='currentColor'
      stroke-width='1.75'
      stroke-linecap='round'
      stroke-linejoin='round'
      aria-hidden='true'
    >
      <path d='M3 17 9 11l4 4 8-8' />
      <path d='M14 7h7v7' />
    </svg>
  )
}

export function DeckComplete ({ points }: { points: number | null }) {
  const showBump = points != null && points > 0
  const floored = showBump ? Math.floor(points) : 0
  const [showMeta, setShowMeta] = useState(() => !showBump || prefersReducedMotion())

  useEffect(() => {
    if (!showBump || prefersReducedMotion()) {
      setShowMeta(true)
    }
  }, [showBump])

  return (
    <section class='caught-up deck-complete'>
      <h1 class='caught-up-title'>Deck complete</h1>
      {showBump
        ? (
          <div
            class='learner-score-bump'
            aria-live='polite'
            aria-label={`Learner score increased by ${floored}`}
          >
            <p
              class={`learner-score-bump-delta${prefersReducedMotion() ? ' instant' : ''}`}
              onAnimationEnd={() => setShowMeta(true)}
            >
              +{floored}
            </p>
            <div class={`learner-score-bump-meta${showMeta ? ' visible' : ''}`}>
              <p class='learner-score-bump-label'>Learner score increased</p>
              <TrendingUpIcon />
            </div>
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
