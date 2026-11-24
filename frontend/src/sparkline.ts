/** Build an SVG path for a sparkline. Empty input yields an empty string. */
export function sparklinePath (
  values: number[],
  width: number,
  height: number,
  padding = 2
): string {
  if (values.length === 0 || width <= 0 || height <= 0) return ''

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min
  const innerWidth = Math.max(width - padding * 2, 0)
  const innerHeight = Math.max(height - padding * 2, 0)

  const points = values.map((value, index) => {
    const x =
      values.length === 1
        ? padding + innerWidth / 2
        : padding + (index / (values.length - 1)) * innerWidth
    const y =
      span === 0
        ? padding + innerHeight / 2
        : padding + innerHeight - ((value - min) / span) * innerHeight
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })

  return `M ${points.join(' L ')}`
}

export function floorScore (score: number): number {
  return Math.floor(score)
}
