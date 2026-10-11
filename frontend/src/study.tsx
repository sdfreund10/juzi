import { useEffect, useState } from 'preact/hooks'
import {
  ApiError,
  createSession,
  rateCard,
  type Difficulty,
  type StudyCard,
  type StudySession,
} from './api'
import { CaughtUp } from './caughtUp'
import { navigate } from './routes'
import {
  cardPrompt,
  cardReveal,
  gradeEasy,
  gradeHard,
  type DisplayLine,
} from './studyCard'
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

function lineClass(line: DisplayLine, role: 'prompt' | 'answer'): string {
  const parts = [role === 'prompt' ? 'prompt-line' : 'answer-line', line.kind]
  if (line.kind === 'chinese') parts.push('zh')
  return parts.join(' ')
}

function DisplayLines({
  lines,
  role,
}: {
  lines: DisplayLine[]
  role: 'prompt' | 'answer'
}) {
  const paired = role === 'prompt' && lines.length === 2
  const linesBody = lines.map((line) => (
    <p key={`${line.kind}-${line.text}`} class={lineClass(line, role)}>
      {line.text}
    </p>
  ))
  return (
    <div class={role === 'prompt' ? 'prompt-block' : 'answer'}>
      {paired ? <div class="prompt-pair">{linesBody}</div> : linesBody}
    </div>
  )
}

function StudySessionView({ session }: { session: StudySession }) {
  const [queue, setQueue] = useState<StudyCard[]>(() => [...session.cards])
  const [revealed, setRevealed] = useState(false)

  const card = queue[0]
  if (!card) {
    return <CaughtUp />
  }

  const modeLabel = MODE_LABELS[card.mode] ?? card.mode
  const promptLines = cardPrompt(card)
  const revealLines = cardReveal(card)

  function onGrade(hard: boolean) {
    const wordId = card.word_id
    setQueue((prev) => (hard ? gradeHard(prev) : gradeEasy(prev)))
    setRevealed(false)
    void rateCard(wordId, hard ? 'hard' : 'easy').catch((err: unknown) => {
      console.error('Failed to persist card grade', err)
    })
  }

  return (
    <div class={`study-shell${revealed ? ' revealed' : ''}`}>
      <div class="study-top">
        <div class="study-top-main">
          <span class="chip">{modeLabel}</span>
          <span class="muted">
            {queue.length} / {session.total}
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

      {revealed ? (
        <>
          <div class="study-body">
            <DisplayLines lines={promptLines} role="prompt" />
            <DisplayLines lines={revealLines} role="answer" />
          </div>
          <div class="grade-zones" aria-label="Grade card">
            <button
              type="button"
              class="grade-zone hard"
              onClick={() => onGrade(true)}
            >
              Hard
              <small>back soon</small>
            </button>
            <button
              type="button"
              class="grade-zone easy"
              onClick={() => onGrade(false)}
            >
              Easy
              <small>later</small>
            </button>
          </div>
        </>
      ) : (
        <div
          class="study-body reveal-target"
          onClick={() => setRevealed(true)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              setRevealed(true)
            }
          }}
        >
          <DisplayLines lines={promptLines} role="prompt" />
          <p class="hint">Tap anywhere to reveal</p>
        </div>
      )}
    </div>
  )
}

export function Study({ categoryId, difficulties }: StudyProps) {
  const { category, ready, missing, error: categoryError } = useCategory(categoryId)
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
    if (!ready || missing || categoryError) return

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
  }, [ready, missing, categoryError, categoryId, difficultyKey])

  if (categoryError) {
    return (
      <>
        <h1 class="title">Building deck</h1>
        <p class="error" role="alert" aria-live="polite">
          {categoryError}
        </p>
        <div class="picker-actions">
          <button
            type="button"
            class="cta"
            onClick={() => navigate({ name: 'home' }, { replace: true })}
          >
            Back
          </button>
        </div>
      </>
    )
  }

  if (!ready || !category) {
    return <p class="building-status">Loading…</p>
  }

  if (empty) {
    return <CaughtUp />
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

  return <StudySessionView session={session} />
}
