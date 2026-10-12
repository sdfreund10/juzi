export type SessionProgress = {
  easyCount: number
  hardIds: number[]
}

export function emptyProgress(): SessionProgress {
  return { easyCount: 0, hardIds: [] }
}

export function recordEasy(
  progress: SessionProgress,
  wordId: number,
): SessionProgress {
  return {
    easyCount: progress.easyCount + 1,
    hardIds: progress.hardIds.filter((id) => id !== wordId),
  }
}

export function recordHard(
  progress: SessionProgress,
  wordId: number,
): SessionProgress {
  if (progress.hardIds.includes(wordId)) return progress
  return { ...progress, hardIds: [...progress.hardIds, wordId] }
}

export function StudyProgress({
  total,
  progress,
}: {
  total: number
  progress: SessionProgress
}) {
  const easyPct = total > 0 ? (progress.easyCount / total) * 100 : 0
  const hardPct = total > 0 ? (progress.hardIds.length / total) * 100 : 0

  return (
    <div
      class="study-progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={progress.easyCount}
      aria-label={
        total > 0 && progress.easyCount >= total
          ? 'Session complete'
          : 'Session progress'
      }
    >
      <span class="study-progress-easy" style={{ width: `${easyPct}%` }} />
      <span class="study-progress-hard" style={{ width: `${hardPct}%` }} />
    </div>
  )
}
