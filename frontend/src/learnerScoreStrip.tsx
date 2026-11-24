import type { LearnerScoreSnapshot } from './api'
import { floorScore, sparklinePath } from './sparkline'

const SPARK_WIDTH = 72
const SPARK_HEIGHT = 22

export function LearnerScoreStrip ({
  snapshot
}: {
  snapshot: LearnerScoreSnapshot
}) {
  const display = floorScore(snapshot.score)
  const values = snapshot.days.map((point) => point.score)
  const path = sparklinePath(values, SPARK_WIDTH, SPARK_HEIGHT)

  return (
    <div class='learner-score-strip'>
      <svg
        class='learner-score-sparkline'
        width={SPARK_WIDTH}
        height={SPARK_HEIGHT}
        viewBox={`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`}
        aria-hidden='true'
      >
        {path
          ? (
            <path
              d={path}
              fill='none'
              stroke='currentColor'
              stroke-width='1.75'
              stroke-linecap='round'
              stroke-linejoin='round'
            />
            )
          : null}
      </svg>
      <div class='learner-score-strip-text'>
        <p class='learner-score-strip-label'>Learner score</p>
        <p class='learner-score-strip-value'>{display}</p>
      </div>
    </div>
  )
}
