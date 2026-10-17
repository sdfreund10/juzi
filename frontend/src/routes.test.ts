import { describe, expect, it } from 'vitest'
import {
  parseDifficulties,
  parsePath,
  pathFor,
  serializeDifficulties
} from './routes'

describe('difficulty slugs', () => {
  it('serializes in canonical order', () => {
    expect(serializeDifficulties(['advanced', 'novice'])).toBe('novice-advanced')
  })

  it('parses known slugs', () => {
    expect(parseDifficulties('novice-intermediate')).toEqual(['novice', 'intermediate'])
  })

  it('rejects unknown or duplicate parts', () => {
    expect(parseDifficulties('beginner')).toBeNull()
    expect(parseDifficulties('novice-novice')).toBeNull()
  })
})

describe('parsePath / pathFor', () => {
  it('round-trips home', () => {
    expect(parsePath('/')).toEqual({ name: 'home' })
    expect(pathFor({ name: 'home' })).toBe('/')
  })

  it('round-trips install', () => {
    expect(parsePath('/install')).toEqual({ name: 'install' })
    expect(parsePath('/install/')).toEqual({ name: 'install' })
    expect(pathFor({ name: 'install' })).toBe('/install')
  })

  it('round-trips proficiency', () => {
    expect(parsePath('/proficiency')).toEqual({ name: 'proficiency' })
    expect(pathFor({ name: 'proficiency' })).toBe('/proficiency')
  })

  it('parses session-new', () => {
    expect(parsePath('/category/12/sessions/new')).toEqual({
      name: 'session-new',
      categoryId: 12
    })
  })

  it('parses session with difficulties', () => {
    expect(parsePath('/category/3/sessions/novice-advanced')).toEqual({
      name: 'session',
      categoryId: 3,
      difficulties: ['novice', 'advanced']
    })
  })

  it('falls back to home for unknown paths', () => {
    expect(parsePath('/nope')).toEqual({ name: 'home' })
    expect(parsePath('/category/abc/sessions/new')).toEqual({ name: 'home' })
  })
})
