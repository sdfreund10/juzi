import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'
import { finishSessionTiming, startSessionTiming, withSessionTiming } from './monitoring'
import {
  ApiError,
  createSession,
  flagWord,
  type Difficulty,
  type StudySession,
} from './api'
import { brandMarkSrc } from './brandMark.ts'
import { CaughtUp } from './caughtUp'
import { navigate } from './routes'
import {
  cardPrompt,
  cardReveal,
  highlightHeadword,
  type DisplayBlock,
  type DisplayLine,
} from './studyCard'
import { StudyProgress } from './studyProgress'
import { useCategory } from './useCategories'
import { useGrading } from './useGrading'

type StudyProps = {
  categoryId: number
  difficulties: Difficulty[]
}

function lineClass(
  line: DisplayLine,
  face: 'prompt' | 'answer',
  blockRole: DisplayBlock['role'],
): string {
  const parts = [
    face === 'prompt' ? 'prompt-line' : 'answer-line',
    line.kind,
  ]
  if (line.kind === 'chinese') parts.push('zh')
  if (blockRole === 'example') parts.push('example')
  return parts.join(' ')
}

function LineText({
  line,
  blockRole,
  headword,
}: {
  line: DisplayLine
  blockRole: DisplayBlock['role']
  headword: string
}) {
  if (blockRole !== 'example' || line.kind !== 'chinese') {
    return line.text
  }
  return highlightHeadword(line.text, headword).map((segment, index) =>
    segment.focus ? (
      <span key={`${index}-${segment.text}`} class="example-focus">
        {segment.text}
      </span>
    ) : (
      <span key={`${index}-${segment.text}`}>{segment.text}</span>
    ),
  )
}

function DisplayBlocks({
  blocks,
  face,
  headword,
}: {
  blocks: DisplayBlock[]
  face: 'prompt' | 'answer'
  headword: string
}) {
  return (
    <div class={face === 'prompt' ? 'prompt-block' : 'answer'}>
      {blocks.map((block) => {
        const paired =
          block.role === 'word' &&
          block.lines.length === 2 &&
          block.lines[0]?.kind === 'chinese' &&
          block.lines[1]?.kind === 'pinyin'
        const linesBody = block.lines.map((line) => (
          <p
            key={`${block.role}-${line.kind}-${line.text}`}
            class={lineClass(line, face, block.role)}
          >
            <LineText
              line={line}
              blockRole={block.role}
              headword={headword}
            />
          </p>
        ))
        return (
          <div
            key={`${block.role}-${block.lines.map((l) => l.text).join('|')}`}
            class={`card-block card-block-${block.role}`}
          >
            {paired ? <div class="prompt-pair">{linesBody}</div> : linesBody}
          </div>
        )
      })}
    </div>
  )
}

function StudySessionView({ session }: { session: StudySession }) {
  const [revealed, setRevealed] = useState(false)
  const [flagged, setFlagged] = useState(false)
  const [confirmFlag, setConfirmFlag] = useState(false)
  const { queue, progress, canUndo, undoing, grade, undo } = useGrading(session.cards)
  const bodyRef = useRef<HTMLDivElement>(null)

  const card = queue[0]
  const done = !card

  useLayoutEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0
  }, [card, revealed])

  useEffect(() => {
    setFlagged(false)
    setConfirmFlag(false)
  }, [card?.word_id])

  function onGrade(hard: boolean) {
    if (!card || !revealed || undoing) return
    grade(card, hard)
    setRevealed(false)
    setConfirmFlag(false)
  }

  async function onUndo() {
    setConfirmFlag(false)
    if (await undo()) {
      setRevealed(true)
    }
  }

  function onFlag() {
    if (!card || flagged || undoing) return
    setConfirmFlag(true)
  }

  function onConfirmFlag() {
    if (!card || flagged || undoing) return
    const wordId = card.word_id
    setConfirmFlag(false)
    void flagWord(wordId)
      .then(() => setFlagged(true))
      .catch(() => {
        // flagWord shows the failure toast.
      })
  }

  return (
    <div class={`study-shell${revealed && !done ? ' revealed' : ''}`}>
      <div class="study-top">
        <StudyProgress total={session.total} progress={progress} />
        <div class="study-top-bar">
          <p class="study-category">
            <img
              class="brand-mark study-mark"
              src={brandMarkSrc}
              alt=""
              width="22"
              height="22"
            />
            <span class="study-category-name">{session.category.name}</span>
          </p>
          <button
            type="button"
            class="text-btn study-close"
            aria-label="Exit"
            onClick={() => navigate({ name: 'home' })}
          >
            ×
          </button>
        </div>
      </div>

      <div class="study-actions" role="group" aria-label="Card actions">
        <button
          type="button"
          class="study-action study-undo"
          aria-label="Undo last rating"
          disabled={!canUndo || undoing}
          onClick={onUndo}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M9 4 4 9l5 5M4 9h10a6 6 0 0 1 0 12h-3" />
          </svg>
          {undoing ? 'Undoing…' : 'Undo'}
        </button>
        {revealed && !done ? (
          <button
            type="button"
            class="study-action study-flag"
            aria-label={flagged ? 'Flagged for review' : 'Flag for review'}
            aria-pressed={flagged}
            disabled={flagged || undoing}
            onClick={onFlag}
          >
            <img
              class="study-flag-icon"
              src={flagged ? '/icons/flag-filled.png' : '/icons/flag-outline.png'}
              alt=""
              width="14"
              height="14"
            />
          </button>
        ) : null}
      </div>

      {done ? (
        <div class="study-body">
          <CaughtUp />
        </div>
      ) : revealed ? (
        <>
          <div
            class="study-body"
            ref={bodyRef}
            role="region"
            aria-label="Study card"
            tabIndex={0}
          >
            <DisplayBlocks
              blocks={cardPrompt(card)}
              face="prompt"
              headword={card.answer_chinese}
            />
            <DisplayBlocks
              blocks={cardReveal(card)}
              face="answer"
              headword={card.answer_chinese}
            />
          </div>
          <div class="grade-zones" aria-label="Grade card">
            <button
              type="button"
              class="grade-zone hard"
              disabled={undoing}
              onClick={() => onGrade(true)}
            >
              Hard
              <small>back soon</small>
            </button>
            <button
              type="button"
              class="grade-zone easy"
              disabled={undoing}
              onClick={() => onGrade(false)}
            >
              Easy
              <small>later</small>
            </button>
          </div>
          {confirmFlag ? (
            <div
              class="study-flag-confirm"
              role="dialog"
              aria-modal="true"
              aria-describedby="flag-confirm-copy"
            >
              <div class="study-flag-confirm-panel">
                <p id="flag-confirm-copy">
                  This will notify the team there may be a problem with this
                  study card.
                </p>
                <div class="study-flag-confirm-actions">
                  <button
                    type="button"
                    class="btn ghost"
                    onClick={() => setConfirmFlag(false)}
                  >
                    Cancel
                  </button>
                  <button type="button" class="btn" onClick={onConfirmFlag}>
                    Flag
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <div
          class="study-body reveal-target"
          ref={bodyRef}
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
          <DisplayBlocks
            blocks={cardPrompt(card)}
            face="prompt"
            headword={card.answer_chinese}
          />
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

    async function build() {
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
