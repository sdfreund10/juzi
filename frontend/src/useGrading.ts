import { useRef, useState } from 'preact/hooks'
import {
  ApiError,
  rateCard,
  undoRating,
  type CardProgress,
  type StudyCard,
} from './api'
import { gradeEasy, gradeHard } from './studyCard'
import {
  emptyProgress,
  recordEasy,
  recordHard,
  type SessionProgress,
} from './studyProgress'
import { showToast } from './toast'

type RatingCheckpoint = {
  queue: StudyCard[]
  progress: SessionProgress
  card: StudyCard
  lastPracticedAt: string
  savedRating: Promise<void>
}

function progressAfterHard(progress: CardProgress, lastPracticedAt: string): CardProgress {
  return {
    ...progress,
    easy_streak: 0,
    due_on: lastPracticedAt.slice(0, 10),
    last_practiced_at: lastPracticedAt,
  }
}

export function useGrading(cards: StudyCard[]) {
  const [queue, setQueue] = useState<StudyCard[]>(() => [...cards])
  const [progress, setProgress] = useState(emptyProgress)
  // Right now just store one checkpoint for the latest graded card.
  const [checkpoint, setCheckpoint] = useState<RatingCheckpoint | null>(null)
  const [undoing, setUndoing] = useState(false)
  const undoInFlight = useRef(false)
  // Pending serves as a request queue. Append new requests by chaining via a then().
  const pendingSave = useRef<Promise<void>>(Promise.resolve())

  function grade(card: StudyCard, hard: boolean) {
    if (undoInFlight.current) return

    const lastPracticedAt = new Date().toISOString()

    // Add the rating to the request queue.
    const savedRating = pendingSave.current.then(() =>
      rateCard(card.word_id, hard ? 'hard' : 'easy', lastPracticedAt),
    )
    // Keep saves ordered without making the learner wait before the next card.
    pendingSave.current = savedRating.catch(() => {
      setCheckpoint((current) => current?.savedRating === savedRating ? null : current)
    })
  
    setCheckpoint({ queue, progress, card, lastPracticedAt, savedRating })
    setProgress((current) =>
      hard ? recordHard(current, card.word_id) : recordEasy(current, card.word_id),
    )
    setQueue((current) => {
      if (!hard) return gradeEasy(current)
      const ratedCard = {
        ...card,
        progress: progressAfterHard(card.progress, lastPracticedAt),
      }
      return gradeHard([ratedCard, ...current.slice(1)])
    })
  }

  async function undo(): Promise<boolean> {
    if (!checkpoint || undoInFlight.current) return false

    undoInFlight.current = true
    setUndoing(true)
    try {
      try {
        // Wait for the rating to be saved before attempting to undo.
        await checkpoint.savedRating
      } catch {
        return false
      }
      await undoRating(
        checkpoint.card.word_id,
        checkpoint.lastPracticedAt,
        checkpoint.card.progress,
      )
      setQueue(checkpoint.queue)
      setProgress(checkpoint.progress)
      setCheckpoint(null)
      return true
    } catch (err) {
      showToast(
        err instanceof ApiError && err.status === 409
          ? 'A newer rating was saved. This rating can’t be undone.'
          : 'Couldn’t undo the rating. Try again.',
      )
      return false
    } finally {
      undoInFlight.current = false
      setUndoing(false)
    }
  }

  return { queue, progress, canUndo: checkpoint !== null, undoing, grade, undo }
}
