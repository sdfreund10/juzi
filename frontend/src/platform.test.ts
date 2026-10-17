import { describe, expect, it } from 'vitest'
import { isIosDevice, isStandaloneDisplay } from './platform'

describe('isIosDevice', () => {
  it('detects iPhone and iPad user agents', () => {
    expect(
      isIosDevice({
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
        platform: 'iPhone',
        maxTouchPoints: 5
      })
    ).toBe(true)
    expect(
      isIosDevice({
        userAgent: 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X)',
        platform: 'iPad',
        maxTouchPoints: 5
      })
    ).toBe(true)
  })

  it('detects iPadOS desktop-UA spoof', () => {
    expect(
      isIosDevice({
        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        platform: 'MacIntel',
        maxTouchPoints: 5
      })
    ).toBe(true)
  })

  it('rejects desktop Mac and Android', () => {
    expect(
      isIosDevice({
        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        platform: 'MacIntel',
        maxTouchPoints: 0
      })
    ).toBe(false)
    expect(
      isIosDevice({
        userAgent: 'Mozilla/5.0 (Linux; Android 14)',
        platform: 'Linux armv8l',
        maxTouchPoints: 5
      })
    ).toBe(false)
  })
})

describe('isStandaloneDisplay', () => {
  it('is true when navigator.standalone is set', () => {
    expect(isStandaloneDisplay({ standalone: true }, { matches: false })).toBe(true)
  })

  it('is true when display-mode is standalone', () => {
    expect(isStandaloneDisplay({}, { matches: true })).toBe(true)
  })

  it('is false in a normal browser tab', () => {
    expect(isStandaloneDisplay({ standalone: false }, { matches: false })).toBe(false)
  })
})
