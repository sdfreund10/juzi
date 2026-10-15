import { describe, expect, it } from 'vitest'
import type { StudyCard } from './api'
import {
  cardPrompt,
  cardReveal,
  gradeEasy,
  gradeHard,
  highlightHeadword,
} from './studyCard'

function card(overrides: Partial<StudyCard> = {}): StudyCard {
  return {
    word_id: 1,
    mode: 'pinyin_to_en',
    answer_chinese: '圖書館',
    answer_pinyin: 'túshūguǎn',
    answer_english: 'library',
    example_chinese: '圖書館很大。',
    example_pinyin: 'Túshūguǎn hěn dà.',
    example_english: 'The library is very big.',
    ...overrides,
  }
}

describe('cardPrompt / cardReveal', () => {
  it('lvl 1 pinyin_to_en: word + sentence clue, English reveal', () => {
    const c = card({ mode: 'pinyin_to_en' })
    expect(cardPrompt(c)).toEqual([
      {
        role: 'word',
        lines: [
          { text: '圖書館', kind: 'chinese' },
          { text: 'túshūguǎn', kind: 'pinyin' },
        ],
      },
      {
        role: 'example',
        lines: [
          { text: '圖書館很大。', kind: 'chinese' },
          { text: 'Túshūguǎn hěn dà.', kind: 'pinyin' },
        ],
      },
    ])
    expect(cardReveal(c)).toEqual([
      {
        role: 'word',
        lines: [{ text: 'library', kind: 'english' }],
      },
      {
        role: 'example',
        lines: [{ text: 'The library is very big.', kind: 'english' }],
      },
    ])
  })

  it('lvl 2 en_to_zh: English clue, Chinese reveal', () => {
    const c = card({ mode: 'en_to_zh' })
    expect(cardPrompt(c)).toEqual([
      {
        role: 'word',
        lines: [{ text: 'library', kind: 'english' }],
      },
      {
        role: 'example',
        lines: [{ text: 'The library is very big.', kind: 'english' }],
      },
    ])
    expect(cardReveal(c)).toEqual([
      {
        role: 'word',
        lines: [
          { text: '圖書館', kind: 'chinese' },
          { text: 'túshūguǎn', kind: 'pinyin' },
        ],
      },
      {
        role: 'example',
        lines: [
          { text: '圖書館很大。', kind: 'chinese' },
          { text: 'Túshūguǎn hěn dà.', kind: 'pinyin' },
        ],
      },
    ])
  })

  it('lvl 3 zh_to_en: characters only clue, pinyin + English reveal', () => {
    const c = card({ mode: 'zh_to_en' })
    expect(cardPrompt(c)).toEqual([
      {
        role: 'word',
        lines: [{ text: '圖書館', kind: 'chinese' }],
      },
      {
        role: 'example',
        lines: [{ text: '圖書館很大。', kind: 'chinese' }],
      },
    ])
    expect(cardReveal(c)).toEqual([
      {
        role: 'word',
        lines: [
          { text: 'túshūguǎn', kind: 'pinyin' },
          { text: 'library', kind: 'english' },
        ],
      },
      {
        role: 'example',
        lines: [
          { text: 'Túshūguǎn hěn dà.', kind: 'pinyin' },
          { text: 'The library is very big.', kind: 'english' },
        ],
      },
    ])
  })

  it('omits the example block when the sentence is empty', () => {
    const c = card({
      mode: 'pinyin_to_en',
      example_chinese: '',
      example_pinyin: '',
      example_english: '',
    })
    expect(cardPrompt(c)).toEqual([
      {
        role: 'word',
        lines: [
          { text: '圖書館', kind: 'chinese' },
          { text: 'túshūguǎn', kind: 'pinyin' },
        ],
      },
    ])
    expect(cardReveal(c)).toEqual([
      {
        role: 'word',
        lines: [{ text: 'library', kind: 'english' }],
      },
    ])
  })
})

describe('highlightHeadword', () => {
  it('accents each occurrence of the headword', () => {
    expect(highlightHeadword('圖書館很大。', '圖書館')).toEqual([
      { text: '圖書館', focus: true },
      { text: '很大。', focus: false },
    ])
    expect(highlightHeadword('愛愛愛', '愛')).toEqual([
      { text: '愛', focus: true },
      { text: '愛', focus: true },
      { text: '愛', focus: true },
    ])
  })

  it('returns the sentence unchanged when the headword is missing', () => {
    expect(highlightHeadword('我們互相幫助。', '互助')).toEqual([
      { text: '我們互相幫助。', focus: false },
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
