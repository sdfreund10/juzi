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

  it('parses card by id', () => {
    expect(parsePath('/cards/zh_to_en/4821')).toEqual({
      name: 'card',
      mode: 'zh_to_en',
      wordId: 4821
    })
    expect(pathFor({ name: 'card', mode: 'zh_to_en', wordId: 4821 })).toBe(
      '/cards/zh_to_en/4821'
    )
  })

  it('accepts an optional trailing character on card id routes', () => {
    expect(parsePath('/cards/zh_to_en/4821/的')).toEqual({
      name: 'card',
      mode: 'zh_to_en',
      wordId: 4821,
      trailing: '的'
    })
    expect(
      pathFor({
        name: 'card',
        mode: 'zh_to_en',
        wordId: 4821,
        trailing: '的'
      })
    ).toBe('/cards/zh_to_en/4821/的')
    expect(pathFor({ name: 'card', mode: 'zh_to_en', wordId: 4821 })).toBe(
      '/cards/zh_to_en/4821'
    )
  })

  it('parses card character lookup', () => {
    expect(parsePath('/cards/en_to_zh/的')).toEqual({
      name: 'card-lookup',
      mode: 'en_to_zh',
      chinese: '的'
    })
    expect(parsePath('/cards/en_to_zh/%E7%9A%84')).toEqual({
      name: 'card-lookup',
      mode: 'en_to_zh',
      chinese: '的'
    })
    expect(
      pathFor({ name: 'card-lookup', mode: 'en_to_zh', chinese: '的' })
    ).toBe('/cards/en_to_zh/的')
  })

  it('rejects unknown card modes', () => {
    expect(parsePath('/cards/latin_to_zh/4821')).toEqual({ name: 'home' })
    expect(parsePath('/cards/latin_to_zh/的')).toEqual({ name: 'home' })
  })
})
