import { describe, expect, it } from 'vitest'
import {
  parseDifficulties,
  parsePath,
  pathFor,
  serializeDifficulties,
} from './routes'

describe('difficulty slugs', () => {
  it('serializes in canonical order', () => {
    expect(serializeDifficulties(['advanced', 'beginner'])).toBe('beginner-advanced')
  })

  it('parses known slugs', () => {
    expect(parseDifficulties('beginner-intermediate')).toEqual([
      'beginner',
      'intermediate',
    ])
  })

  it('rejects unknown or duplicate parts', () => {
    expect(parseDifficulties('expert')).toBeNull()
    expect(parseDifficulties('beginner-beginner')).toBeNull()
  })
})

describe('parsePath / pathFor', () => {
  it('round-trips home', () => {
    expect(parsePath('/')).toEqual({ name: 'home' })
    expect(pathFor({ name: 'home' })).toBe('/')
  })

  it('parses session-new', () => {
    expect(parsePath('/category/12/sessions/new')).toEqual({
      name: 'session-new',
      categoryId: 12,
    })
  })

  it('parses session with difficulties', () => {
    expect(parsePath('/category/3/sessions/beginner-advanced')).toEqual({
      name: 'session',
      categoryId: 3,
      difficulties: ['beginner', 'advanced'],
    })
  })

  it('falls back to home for unknown paths', () => {
    expect(parsePath('/nope')).toEqual({ name: 'home' })
    expect(parsePath('/category/abc/sessions/new')).toEqual({ name: 'home' })
  })
})
