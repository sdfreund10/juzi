import { describe, expect, it } from 'vitest'
import { emptyProgress, recordEasy, recordHard } from './studyProgress'

describe('recordEasy / recordHard', () => {
  it('starts with no easy or hard cards', () => {
    expect(emptyProgress()).toEqual({ easyCount: 0, hardIds: [] })
  })

  it('counts an unseen card as easy and leaves hard empty', () => {
    expect(recordEasy(emptyProgress(), 1)).toEqual({
      easyCount: 1,
      hardIds: []
    })
  })

  it('adds an unseen card to the hard list', () => {
    expect(recordHard(emptyProgress(), 1)).toEqual({
      easyCount: 0,
      hardIds: [1]
    })
  })

  it('does not grow the hard list when the same card is marked hard again', () => {
    const once = recordHard(emptyProgress(), 1)
    expect(recordHard(once, 1)).toEqual(once)
  })

  it('moves a hard card to easy without changing unseen remainder', () => {
    const afterHard = recordHard(recordHard(emptyProgress(), 1), 2)
    expect(recordEasy(afterHard, 1)).toEqual({
      easyCount: 1,
      hardIds: [2]
    })
  })

  it('only increases the easy count', () => {
    let progress = emptyProgress()
    progress = recordEasy(progress, 1)
    progress = recordHard(progress, 2)
    progress = recordEasy(progress, 2)
    expect(progress.easyCount).toBe(2)
    expect(progress.hardIds).toEqual([])
  })
})
