import { useEffect, useLayoutEffect, useState } from 'preact/hooks'
import { finishSessionTiming, startSessionTiming, withSessionTiming } from './monitoring'
import {
  ApiError,
  createSession,
  type Difficulty,
  type StudySession
} from './api'
import { CaughtUp } from './caughtUp'
import { navigate } from './routes'
import { StudyCardFace, StudyTopBar } from './studyDisplay'
import {
  FlagActionButton,
  FlagConfirmDialog,
  useCardFlag
} from './studyFlag'
import { StudyProgress } from './studyProgress'
import { useCategory } from './useCategories'
import { useGrading } from './useGrading'

type StudyProps = {
  categoryId: number
  difficulties: Difficulty[]
}

function StudySessionView ({ session }: { session: StudySession }) {
  const [revealed, setRevealed] = useState(false)
  const { queue, progress, canUndo, undoing, grade, undo } = useGrading(session.cards)

  const card = queue[0]
  const done = !card
  const {
    flagged,
    confirmFlag,
    requestFlag,
    confirmReason,
    cancelFlag
  } = useCardFlag(card?.word_id ?? null)

  function onGrade (hard: boolean) {
    if (!card || !revealed || undoing) return
    grade(card, hard)
    setRevealed(false)
    cancelFlag()
  }

  async function onUndo () {
    cancelFlag()
    if (await undo()) {
      setRevealed(true)
    }
  }

  return (
    <div class={`study-shell${revealed && !done ? ' revealed' : ''}`}>
      <div class='study-top'>
        <StudyProgress total={session.total} progress={progress} />
        <StudyTopBar title={session.category.name} />
      </div>

      <div class='study-actions' role='group' aria-label='Card actions'>
        <button
          type='button'
          class='study-action study-undo'
          aria-label='Undo last rating'
          disabled={!canUndo || undoing}
          onClick={onUndo}
        >
          <svg
            width='16'
            height='16'
            viewBox='0 0 24 24'
            fill='none'
            stroke='currentColor'
            stroke-width='1.5'
            stroke-linecap='round'
            stroke-linejoin='round'
            aria-hidden='true'
          >
            <path d='M9 4 4 9l5 5M4 9h10a6 6 0 0 1 0 12h-3' />
          </svg>
          {undoing ? 'Undoing…' : 'Undo'}
        </button>
        {revealed && !done
          ? (
            <FlagActionButton
              flagged={flagged}
              disabled={undoing}
              onClick={() => requestFlag({ disabled: undoing })}
            />
            )
          : null}
      </div>

      {done
        ? (
          <div key='caught-up' class='study-body study-card-enter'>
            <CaughtUp />
          </div>
          )
        : (
          <>
            <StudyCardFace
              key={card.word_id}
              card={card}
              revealed={revealed}
              onReveal={() => setRevealed(true)}
              faceKey={card.word_id}
            />
            {revealed
              ? (
                <>
                  <div class='grade-zones' aria-label='Grade card'>
                    <button
                      type='button'
                      class='grade-zone hard'
                      disabled={undoing}
                      onClick={() => onGrade(true)}
                    >
                      Hard
                      <small>back soon</small>
                    </button>
                    <button
                      type='button'
                      class='grade-zone easy'
                      disabled={undoing}
                      onClick={() => onGrade(false)}
                    >
                      Easy
                      <small>later</small>
                    </button>
                  </div>
                  {confirmFlag
                    ? (
                      <FlagConfirmDialog
                        onConfirm={(reason) =>
                          confirmReason(reason, { disabled: undoing })}
                        onCancel={cancelFlag}
                      />
                      )
                    : null}
                </>
                )
              : null}
          </>
          )}
    </div>
  )
}

export function Study ({ categoryId, difficulties }: StudyProps) {
  const { category, ready, missing, error: categoryError } = useCategory(categoryId)
  const [session, setSession] = useState<StudySession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [empty, setEmpty] = useState(false)

  useLayoutEffect(() => {
    startSessionTiming()
    return () => finishSessionTiming('cancelled')
  }, [categoryId, difficulties.join(',')])

  useLayoutEffect(() => {
    if (session) finishSessionTiming('ready')
    else if (empty) finishSessionTiming('empty')
    else if (error || categoryError || missing) finishSessionTiming('failed')
  }, [session, empty, error, categoryError, missing])

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

    async function build () {
      try {
        const next = await withSessionTiming(() => createSession(categoryId, difficulties))
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

    build().catch(() => {})
    return () => {
      cancelled = true
    }
  }, [ready, missing, categoryError, categoryId, difficultyKey])

  if (categoryError) {
    return (
      <>
        <h1 class='title'>Building deck</h1>
        <p class='error' role='alert' aria-live='polite'>
          {categoryError}
        </p>
        <div class='picker-actions'>
          <button
            type='button'
            class='cta'
            onClick={() => navigate({ name: 'home' }, { replace: true })}
          >
            Back
          </button>
        </div>
      </>
    )
  }

  if (!ready || !category) {
    return <p class='building-status'>Loading…</p>
  }

  if (empty) {
    return <CaughtUp />
  }

  if (error) {
    return (
      <>
        <h1 class='title'>Building deck</h1>
        <p class='subtitle'>{category.name}</p>
        <p class='error' role='alert' aria-live='polite'>
          {error}
        </p>
        <div class='picker-actions'>
          <button
            type='button'
            class='cta'
            onClick={() =>
              navigate(
                { name: 'session-new', categoryId: category.id },
                { replace: true }
              )}
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
        <h1 class='title'>Building deck</h1>
        <p class='subtitle'>{category.name}</p>
        <p class='building-status' aria-live='polite'>
          Gathering cards…
        </p>
      </>
    )
  }

  return <StudySessionView session={session} />
}
