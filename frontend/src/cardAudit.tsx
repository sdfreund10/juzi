import { type ComponentChildren } from 'preact'
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'
import {
  ApiError,
  fetchWord,
  flagWord,
  lookupWords,
  type FlagReason,
  type StudyCard,
  type WordDetail
} from './api'
import { brandMarkSrc } from './brandMark.ts'
import { navigate, STUDY_MODES, type StudyMode } from './routes'
import { cardPrompt, cardReveal } from './studyCard'
import { DisplayBlocks } from './studyDisplay'

const MODE_LABELS: Record<StudyMode, string> = {
  pinyin_to_en: 'Pinyin to English',
  en_to_zh: 'English to Chinese',
  zh_to_en: 'Chinese to English'
}

const FLAG_REASONS: { value: FlagReason, label: string }[] = [
  { value: 'wrong_deck', label: 'Wrong deck' },
  { value: 'bad_translation', label: 'Bad translation' },
  { value: 'bad_example', label: 'Bad example' },
  { value: 'other', label: 'Other' }
]

const EMPTY_PROGRESS = {
  easy_streak: 0,
  easy_count: 0,
  due_on: null,
  last_practiced_at: null
}

function studyCardFromWord (word: WordDetail, mode: StudyMode): StudyCard {
  return {
    word_id: word.id,
    mode,
    answer_chinese: word.chinese,
    answer_pinyin: word.pinyin,
    answer_english: word.english_basic,
    example_chinese: word.example_chinese,
    example_pinyin: word.example_pinyin,
    example_english: word.example_english,
    progress: EMPTY_PROGRESS
  }
}

function AuditChrome ({
  title,
  children
}: {
  title: string
  children: ComponentChildren
}) {
  return (
    <div class='study-shell audit-shell'>
      <div class='study-top'>
        <div class='study-top-bar'>
          <p class='study-category'>
            <img
              class='brand-mark study-mark'
              src={brandMarkSrc}
              alt=''
              width='22'
              height='22'
            />
            <span class='study-category-name'>{title}</span>
          </p>
          <button
            type='button'
            class='text-btn study-close'
            aria-label='Exit'
            onClick={() => navigate({ name: 'home' })}
          >
            ×
          </button>
        </div>
      </div>
      {children}
    </div>
  )
}

function ModeSwitcher ({ mode, wordId }: { mode: StudyMode; wordId: number }) {
  return (
    <div class='audit-modes' role='group' aria-label='Study mode'>
      {STUDY_MODES.map((option) => (
        <button
          key={option}
          type='button'
          class={`audit-mode${option === mode ? ' active' : ''}`}
          aria-pressed={option === mode}
          onClick={() => {
            if (option === mode) return
            navigate({ name: 'card', mode: option, wordId })
          }}
        >
          {MODE_LABELS[option]}
        </button>
      ))}
    </div>
  )
}

function AuditCardView ({ word, mode }: { word: WordDetail; mode: StudyMode }) {
  const [revealed, setRevealed] = useState(false)
  const [flagged, setFlagged] = useState(false)
  const [confirmFlag, setConfirmFlag] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)
  const card = studyCardFromWord(word, mode)

  useLayoutEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0
  }, [word.id, mode, revealed])

  useEffect(() => {
    setRevealed(false)
    setFlagged(false)
    setConfirmFlag(false)
  }, [word.id, mode])

  function onFlag () {
    if (flagged) return
    setConfirmFlag(true)
  }

  function onConfirmFlag (reason: FlagReason) {
    if (flagged) return
    setConfirmFlag(false)
    flagWord(word.id, reason)
      .then(() => setFlagged(true))
      .catch(() => {
        // flagWord shows the failure toast.
      })
  }

  return (
    <AuditChrome title={`Card ${word.id}`}>
      <ModeSwitcher mode={mode} wordId={word.id} />
      <div class='study-actions' role='group' aria-label='Card actions'>
        {revealed
          ? (
            <button
              type='button'
              class='study-action study-flag'
              aria-label={flagged ? 'Flagged for review' : 'Flag for review'}
              aria-pressed={flagged}
              disabled={flagged}
              onClick={onFlag}
            >
              <img
                class='study-flag-icon'
                src={flagged ? '/icons/flag-filled.png' : '/icons/flag-outline.png'}
                alt=''
                width='14'
                height='14'
              />
            </button>
            )
          : null}
      </div>
      <div
        key={`${word.id}-${mode}`}
        class={`study-body study-card-enter${revealed ? '' : ' reveal-target'}`}
        ref={bodyRef}
        role={revealed ? 'region' : 'button'}
        aria-label={revealed ? 'Study card' : undefined}
        tabIndex={0}
        onClick={revealed ? undefined : () => setRevealed(true)}
        onKeyDown={
          revealed
            ? undefined
            : (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  setRevealed(true)
                }
              }
        }
      >
        <DisplayBlocks
          blocks={cardPrompt(card)}
          face='prompt'
          headword={card.answer_chinese}
        />
        {revealed
          ? (
            <DisplayBlocks
              blocks={cardReveal(card)}
              face='answer'
              headword={card.answer_chinese}
            />
            )
          : (
            <p class='hint'>Tap anywhere to reveal</p>
            )}
      </div>
      {revealed && confirmFlag
        ? (
          <div
            class='study-flag-confirm study-flag-enter'
            role='dialog'
            aria-modal='true'
            aria-labelledby='flag-confirm-copy'
          >
            <div class='study-flag-confirm-panel'>
              <p id='flag-confirm-copy'>What's wrong with this card?</p>
              <div class='study-flag-confirm-actions'>
                {FLAG_REASONS.map(({ value, label }) => (
                  <button
                    key={value}
                    type='button'
                    class='btn study-flag-reason'
                    onClick={() => onConfirmFlag(value)}
                  >
                    {label}
                  </button>
                ))}
                <button
                  type='button'
                  class='btn ghost'
                  onClick={() => setConfirmFlag(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
          )
        : null}
    </AuditChrome>
  )
}

function MatchList ({
  mode,
  chinese,
  matches
}: {
  mode: StudyMode
  chinese: string
  matches: WordDetail[]
}) {
  return (
    <AuditChrome title={chinese}>
      <p class='lede audit-lede'>
        {matches.length} readings for this headword. Pick one.
      </p>
      <ul class='audit-matches'>
        {matches.map((word) => (
          <li key={word.id}>
            <button
              type='button'
              class='audit-match'
              onClick={() => navigate({ name: 'card', mode, wordId: word.id })}
            >
              <span class='audit-match-pinyin'>{word.pinyin}</span>
              <span class='audit-match-english'>{word.english_basic}</span>
              <span class='audit-match-id'>#{word.id}</span>
            </button>
          </li>
        ))}
      </ul>
    </AuditChrome>
  )
}

export function CardById ({ mode, wordId }: { mode: StudyMode; wordId: number }) {
  const [word, setWord] = useState<WordDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let cancelled = false
    setWord(null)
    setError(null)
    setMissing(false)

    fetchWord(wordId)
      .then((next) => {
        if (cancelled) return
        setWord(next)
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setMissing(true)
          return
        }
        setError(
          err instanceof ApiError && err.message
            ? err.message
            : 'Could not load this card.'
        )
      })

    return () => {
      cancelled = true
    }
  }, [wordId])

  if (missing) {
    return (
      <AuditChrome title='Card'>
        <p class='error' role='alert'>
          No word with id {wordId}.
        </p>
      </AuditChrome>
    )
  }

  if (error) {
    return (
      <AuditChrome title='Card'>
        <p class='error' role='alert' aria-live='polite'>
          {error}
        </p>
      </AuditChrome>
    )
  }

  if (!word) {
    return (
      <AuditChrome title='Card'>
        <p class='building-status'>Loading…</p>
      </AuditChrome>
    )
  }

  return <AuditCardView word={word} mode={mode} />
}

export function CardLookup ({
  mode,
  chinese
}: {
  mode: StudyMode
  chinese: string
}) {
  const [matches, setMatches] = useState<WordDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setMatches(null)
    setError(null)

    lookupWords(chinese)
      .then((next) => {
        if (cancelled) return
        if (next.length === 1) {
          navigate(
            { name: 'card', mode, wordId: next[0].id },
            { replace: true }
          )
          return
        }
        setMatches(next)
      })
      .catch((err) => {
        if (cancelled) return
        setError(
          err instanceof ApiError && err.message
            ? err.message
            : 'Could not look up this headword.'
        )
      })

    return () => {
      cancelled = true
    }
  }, [mode, chinese])

  if (error) {
    return (
      <AuditChrome title={chinese}>
        <p class='error' role='alert' aria-live='polite'>
          {error}
        </p>
      </AuditChrome>
    )
  }

  if (matches === null) {
    return (
      <AuditChrome title={chinese}>
        <p class='building-status'>Loading…</p>
      </AuditChrome>
    )
  }

  if (matches.length === 0) {
    return (
      <AuditChrome title={chinese}>
        <p class='error' role='alert'>
          No words match this headword.
        </p>
      </AuditChrome>
    )
  }

  return <MatchList mode={mode} chinese={chinese} matches={matches} />
}
