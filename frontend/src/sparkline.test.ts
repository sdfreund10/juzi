import { describe, expect, it } from 'vitest'
import { floorScore, sparklinePath } from './sparkline'

describe('sparklinePath', () => {
  it('returns an empty string for an empty series', () => {
    expect(sparklinePath([], 100, 20)).toBe('')
  })

  it('places a positive single point at the top of a zero-based scale', () => {
    expect(sparklinePath([5], 100, 20)).toBe('M 50.00,2.00')
  })

  it('draws a flat positive series along the top of a zero-based scale', () => {
    expect(sparklinePath([3, 3, 3], 100, 20)).toBe(
      'M 2.00,2.00 L 50.00,2.00 L 98.00,2.00'
    )
  })

  it('keeps an all-zero series centered', () => {
    expect(sparklinePath([0, 0, 0], 100, 20)).toBe(
      'M 2.00,10.00 L 50.00,10.00 L 98.00,10.00'
    )
  })

  it('maps a rising then falling series above a zero baseline', () => {
    const path = sparklinePath([0, 10, 5], 100, 20)
    expect(path.startsWith('M ')).toBe(true)
    expect(path).toContain(' L ')
    const coords = path
      .replace('M ', '')
      .split(' L ')
      .map((pair) => pair.split(',').map(Number))
    expect(coords).toHaveLength(3)
    expect(coords[0]![1]).toBeGreaterThan(coords[1]![1]!)
    expect(coords[2]![1]).toBeGreaterThan(coords[1]![1]!)
    expect(coords[2]![1]).toBeLessThan(coords[0]![1]!)
  })

  it('does not pin a positive dip to the chart floor', () => {
    const path = sparklinePath([20, 15, 20], 100, 20)
    const coords = path
      .replace('M ', '')
      .split(' L ')
      .map((pair) => pair.split(',').map(Number))
    const bottom = 2 + 16 // padding + innerHeight
    expect(coords[1]![1]).toBeLessThan(bottom)
    expect(coords[1]![1]).toBeGreaterThan(coords[0]![1]!)
  })
})

describe('floorScore', () => {
  it('floors fractional learner scores for display', () => {
    expect(floorScore(12.5)).toBe(12)
    expect(floorScore(10)).toBe(10)
    expect(floorScore(0.9)).toBe(0)
  })
})
