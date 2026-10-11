import type { StudyCard } from './api'

export type DisplayLine = {
  text: string
  kind: 'chinese' | 'pinyin' | 'english'
}

export function cardPrompt(card: StudyCard): DisplayLine[] {
  switch (card.mode) {
    case 'pinyin_to_en':
      return [
        { text: card.answer_chinese, kind: 'chinese' },
        { text: card.answer_pinyin, kind: 'pinyin' },
      ]
    case 'en_to_zh':
      return [{ text: card.answer_english, kind: 'english' }]
    case 'zh_to_en':
      return [{ text: card.answer_chinese, kind: 'chinese' }]
    default:
      return [{ text: card.prompt, kind: 'english' }]
  }
}

export function cardReveal(card: StudyCard): DisplayLine[] {
  switch (card.mode) {
    case 'pinyin_to_en':
      return [{ text: card.answer_english, kind: 'english' }]
    case 'en_to_zh':
      return [
        { text: card.answer_chinese, kind: 'chinese' },
        { text: card.answer_pinyin, kind: 'pinyin' },
      ]
    case 'zh_to_en':
      return [
        { text: card.answer_pinyin, kind: 'pinyin' },
        { text: card.answer_english, kind: 'english' },
      ]
    default:
      return [{ text: card.answer_english, kind: 'english' }]
  }
}

export function gradeHard<T>(
  queue: T[],
  random: () => number = Math.random,
): T[] {
  if (queue.length === 0) return queue
  const [current, ...rest] = queue
  if (rest.length === 0) return [current]
  const minIndex = Math.ceil(rest.length * 0.2)
  const index = minIndex + Math.floor(random() * (rest.length + 1 - minIndex))
  return [...rest.slice(0, index), current, ...rest.slice(index)]
}

export function gradeEasy<T>(queue: T[]): T[] {
  if (queue.length === 0) return queue
  return queue.slice(1)
}
