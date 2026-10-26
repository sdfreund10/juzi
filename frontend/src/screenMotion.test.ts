import { describe, expect, it } from 'vitest'
import { routeDepth, routeKey, screenMotion } from './screenMotion'
import type { Route } from './routes'

const home: Route = { name: 'home' }
const install: Route = { name: 'install' }
const proficiency: Route = { name: 'proficiency' }
const sessionNew: Route = { name: 'session-new', categoryId: 3 }
const session: Route = {
  name: 'session',
  categoryId: 3,
  difficulties: ['novice', 'advanced']
}
const card: Route = { name: 'card', mode: 'zh_to_en', wordId: 4821 }
const cardLookup: Route = { name: 'card-lookup', mode: 'zh_to_en', chinese: '的' }

describe('routeDepth', () => {
  it('places home at the root', () => {
    expect(routeDepth(home)).toBe(0)
  })

  it('places masthead stack screens one level down', () => {
    expect(routeDepth(install)).toBe(1)
    expect(routeDepth(proficiency)).toBe(1)
    expect(routeDepth(sessionNew)).toBe(1)
  })

  it('places study deeper than the deck stack', () => {
    expect(routeDepth(session)).toBe(2)
    expect(routeDepth(card)).toBe(2)
    expect(routeDepth(cardLookup)).toBe(2)
  })
})

describe('routeKey', () => {
  it('keys session by category and difficulties', () => {
    expect(routeKey(session)).toBe('session:3:novice-advanced')
    expect(routeKey(sessionNew)).toBe('session-new:3')
  })

  it('keys card audit routes by mode and id or headword', () => {
    expect(routeKey(card)).toBe('card:zh_to_en:4821')
    expect(routeKey(cardLookup)).toBe('card-lookup:zh_to_en:的')
  })
})

describe('screenMotion', () => {
  it('skips motion for replace navigations and first paint', () => {
    expect(screenMotion(home, proficiency, { skipStack: true })).toBe('none')
    expect(screenMotion(null, home)).toBe('none')
  })

  it('slides forward into the deck stack', () => {
    expect(screenMotion(home, sessionNew)).toBe('forward')
    expect(screenMotion(home, install)).toBe('forward')
    expect(screenMotion(home, proficiency)).toBe('forward')
  })

  it('slides back to decks', () => {
    expect(screenMotion(sessionNew, home)).toBe('back')
    expect(screenMotion(install, home)).toBe('back')
    expect(screenMotion(proficiency, home)).toBe('back')
  })

  it('fades into and out of study', () => {
    expect(screenMotion(sessionNew, session)).toBe('fade')
    expect(screenMotion(home, session)).toBe('fade')
    expect(screenMotion(session, home)).toBe('fade')
    expect(screenMotion(session, sessionNew)).toBe('fade')
  })

  it('skips motion for audit card routes', () => {
    expect(screenMotion(home, card)).toBe('none')
    expect(screenMotion(card, home)).toBe('none')
    expect(screenMotion(home, cardLookup)).toBe('none')
    expect(screenMotion(card, cardLookup)).toBe('none')
  })

  it('stays still across same-depth stack screens', () => {
    expect(screenMotion(install, proficiency)).toBe('none')
    expect(screenMotion(sessionNew, install)).toBe('none')
  })
})
