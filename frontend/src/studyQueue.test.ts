import { describe, expect, it } from 'vitest'
import type { StudyCard } from './api'
import {
  cardPrompt,
  cardReveal,
  gradeEasy,
  gradeHard,
} from './studyCard'

function card(overrides: Partial<StudyCard> = {}): StudyCard {
  return {
    word_id: 1,
    mode: 'pinyin_to_en',
    prompt: 'túshūguǎn',
    answer_chinese: '圖書館',
    answer_pinyin: 'túshūguǎn',
    answer_english: 'library',
    ...overrides,
  }
}

describe('cardPrompt / cardReveal', () => {
  it('lvl 1 pinyin_to_en: characters + pinyin, reveal English', () => {
    const c = card({ mode: 'pinyin_to_en' })
    expect(cardPrompt(c)).toEqual([
      { text: '圖書館', kind: 'chinese' },
      { text: 'túshūguǎn', kind: 'pinyin' },
    ])
    expect(cardReveal(c)).toEqual([{ text: 'library', kind: 'english' }])
  })

  it('lvl 2 en_to_zh: English, reveal characters + pinyin', () => {
    const c = card({ mode: 'en_to_zh' })
    expect(cardPrompt(c)).toEqual([{ text: 'library', kind: 'english' }])
    expect(cardReveal(c)).toEqual([
      { text: '圖書館', kind: 'chinese' },
      { text: 'túshūguǎn', kind: 'pinyin' },
    ])
  })

  it('lvl 3 zh_to_en: characters only, reveal English + pinyin', () => {
    const c = card({ mode: 'zh_to_en' })
    expect(cardPrompt(c)).toEqual([{ text: '圖書館', kind: 'chinese' }])
    expect(cardReveal(c)).toEqual([
      { text: 'túshūguǎn', kind: 'pinyin' },
      { text: 'library', kind: 'english' },
    ])
  })
})

describe('gradeHard / gradeEasy', () => {
  it('reinserts the front card after a ~20% buffer on hard', () => {
    const queue = ['a', 'b', 'c', 'd', 'e', 'f']
    // rest length 5 → minIndex 1; span 5 → indices 1..5
    expect(gradeHard(queue, () => 0)).toEqual(['b', 'a', 'c', 'd', 'e', 'f'])
    expect(gradeHard(queue, () => 0.99)).toEqual(['b', 'c', 'd', 'e', 'f', 'a'])
  })

  it('removes the front card on easy', () => {
    expect(gradeEasy(['a', 'b', 'c'])).toEqual(['b', 'c'])
  })

  it('handles a single-card queue', () => {
    expect(gradeHard(['only'])).toEqual(['only'])
    expect(gradeEasy(['only'])).toEqual([])
  })

  it('leaves an empty queue unchanged', () => {
    expect(gradeHard([])).toEqual([])
    expect(gradeEasy([])).toEqual([])
  })
})
