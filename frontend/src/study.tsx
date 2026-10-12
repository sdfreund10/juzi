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
  highlightHeadword,
  type DisplayBlock,
  type DisplayLine,
} from './studyCard'
import { useCategory } from './useCategories'

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
type SittingGrade = 'easy' | 'hard'

function SittingProgress({
  total,
  grades,
  done,
}: {
  total: number
  grades: SittingGrade[]
  done: boolean
}) {
  const segments = Array.from({ length: total }, (_, index) => {
    if (done) return 'easy' as const
    return grades[index] ?? null
  })

  return (
    <div
      class={`study-progress${done ? ' done' : ''}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done ? total : Math.min(grades.length, total)}
      aria-label={done ? 'Sitting complete' : 'Sitting progress'}
    >
      {segments.map((grade, index) => (
        <span
          key={index}
          class={`study-progress-segment${grade ? ` ${grade}` : ''}`}
        />
      ))}
    </div>
  )
}

function StudySessionView({ session }: { session: StudySession }) {
  const [queue, setQueue] = useState<StudyCard[]>(() => [...session.cards])
  const [revealed, setRevealed] = useState(false)
  const [grades, setGrades] = useState<SittingGrade[]>([])

  const card = queue[0]
  const done = !card

  function onGrade(hard: boolean) {
    if (!card) return
    const wordId = card.word_id
    setGrades((prev) => [...prev, hard ? 'hard' : 'easy'])
    setQueue((prev) => (hard ? gradeHard(prev) : gradeEasy(prev)))
    setRevealed(false)
    void rateCard(wordId, hard ? 'hard' : 'easy').catch((err: unknown) => {
      console.error('Failed to persist card grade', err)
    })
  }

  return (
    <div class={`study-shell${revealed && !done ? ' revealed' : ''}`}>
      <div class="study-top">
        <div class="study-top-main">
          <span class="study-category">{session.category.name}</span>
          <SittingProgress
            total={session.total}
            grades={grades}
            done={done}
          />
        </div>
        <button
          type="button"
          class="text-btn"
          onClick={() => navigate({ name: 'home' })}
        >
          Exit
        </button>
      </div>

      {done ? (
        <CaughtUp />
      ) : revealed ? (
        <>
          <div class="study-body">
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
