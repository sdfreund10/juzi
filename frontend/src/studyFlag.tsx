import { useEffect, useState } from 'preact/hooks'
import { flagWord, type FlagReason } from './api'

const FLAG_REASONS: { value: FlagReason, label: string }[] = [
  { value: 'wrong_deck', label: 'Wrong deck' },
  { value: 'bad_translation', label: 'Bad translation' },
  { value: 'bad_example', label: 'Bad example' },
  { value: 'other', label: 'Other' }
]

export function useCardFlag (wordId: number | null) {
  const [flagged, setFlagged] = useState(false)
  const [confirmFlag, setConfirmFlag] = useState(false)

  useEffect(() => {
    setFlagged(false)
    setConfirmFlag(false)
  }, [wordId])

  function requestFlag (options: { disabled?: boolean } = {}) {
    if (wordId == null || flagged || options.disabled) return
    setConfirmFlag(true)
  }

  function confirmReason (
    reason: FlagReason,
    options: { disabled?: boolean } = {}
  ) {
    if (wordId == null || flagged || options.disabled) return
    setConfirmFlag(false)
    flagWord(wordId, reason)
      .then(() => setFlagged(true))
      .catch(() => {
        // flagWord shows the failure toast.
      })
  }

  function cancelFlag () {
    setConfirmFlag(false)
  }

  return {
    flagged,
    confirmFlag,
    requestFlag,
    confirmReason,
    cancelFlag
  }
}

export function FlagActionButton ({
  flagged,
  disabled = false,
  onClick
}: {
  flagged: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type='button'
      class='study-action study-flag'
      aria-label={flagged ? 'Flagged for review' : 'Flag for review'}
      aria-pressed={flagged}
      disabled={flagged || disabled}
      onClick={onClick}
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
}

export function FlagConfirmDialog ({
  onConfirm,
  onCancel
}: {
  onConfirm: (reason: FlagReason) => void
  onCancel: () => void
}) {
  return (
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
              onClick={() => onConfirm(value)}
            >
              {label}
            </button>
          ))}
          <button type='button' class='btn ghost' onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
