import { type ComponentChildren } from 'preact'
import { useEffect, useState } from 'preact/hooks'
import {
  ApiError,
  fetchWord,
  lookupWords,
  type StudyCard,
  type WordDetail
} from './api'
import { navigate, STUDY_MODES, type StudyMode } from './routes'
import { StudyCardFace, StudyTopBar } from './studyDisplay'
import {
  FlagActionButton,
  FlagConfirmDialog,
  useCardFlag
} from './studyFlag'

const MODE_LABELS: Record<StudyMode, string> = {
  pinyin_to_en: 'Pinyin to English',
  en_to_zh: 'English to Chinese',
  zh_to_en: 'Chinese to English'
}

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
        <StudyTopBar title={title} />
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
  const card = studyCardFromWord(word, mode)
  const {
    flagged,
    confirmFlag,
    requestFlag,
    confirmReason,
    cancelFlag
  } = useCardFlag(word.id)

  useEffect(() => {
    setRevealed(false)
  }, [word.id, mode])

  return (
    <AuditChrome title={`Card ${word.id}`}>
      <ModeSwitcher mode={mode} wordId={word.id} />
      <div class='study-actions' role='group' aria-label='Card actions'>
        {revealed
          ? (
            <FlagActionButton
              flagged={flagged}
              onClick={() => requestFlag()}
            />
            )
          : null}
      </div>
      <StudyCardFace
        key={`${word.id}-${mode}`}
        card={card}
        revealed={revealed}
        onReveal={() => setRevealed(true)}
        faceKey={`${word.id}-${mode}`}
      />
      {revealed && confirmFlag
        ? (
          <FlagConfirmDialog
            onConfirm={confirmReason}
            onCancel={cancelFlag}
          />
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
        {matches.map((match) => (
          <li key={match.id}>
            <button
              type='button'
              class='audit-match'
              onClick={() => navigate({ name: 'card', mode, wordId: match.id })}
            >
              <span class='audit-match-pinyin'>{match.pinyin}</span>
              <span class='audit-match-english'>{match.english_basic}</span>
              <span class='audit-match-id'>#{match.id}</span>
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
