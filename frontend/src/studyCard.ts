import type { StudyCard } from './api'

export type DisplayLine = {
  text: string
  kind: 'chinese' | 'pinyin' | 'english'
}

export type DisplayBlock = {
  role: 'word' | 'example'
  lines: DisplayLine[]
}

export type TextSegment = {
  text: string
  focus: boolean
}

/** Split a Chinese example so the headword can be accented. No match → one plain segment. */
export function highlightHeadword(
  sentence: string,
  headword: string,
): TextSegment[] {
  if (!sentence || !headword || !sentence.includes(headword)) {
    return [{ text: sentence, focus: false }]
  }
  const segments: TextSegment[] = []
  let rest = sentence
  while (rest.length > 0) {
    const index = rest.indexOf(headword)
    if (index < 0) {
      segments.push({ text: rest, focus: false })
      break
    }
    if (index > 0) {
      segments.push({ text: rest.slice(0, index), focus: false })
    }
    segments.push({ text: headword, focus: true })
    rest = rest.slice(index + headword.length)
  }
  return segments
}

function hasExample(card: StudyCard): boolean {
  return Boolean(
    card.example_chinese && card.example_pinyin && card.example_english,
  )
}

export function cardPrompt(card: StudyCard): DisplayBlock[] {
  const example = hasExample(card)

  switch (card.mode) {
    case 'pinyin_to_en': {
      const blocks: DisplayBlock[] = [
        {
          role: 'word',
          lines: [
            { text: card.answer_chinese, kind: 'chinese' },
            { text: card.answer_pinyin, kind: 'pinyin' },
          ],
        },
      ]
      if (example) {
        blocks.push({
          role: 'example',
          lines: [
            { text: card.example_chinese, kind: 'chinese' },
            { text: card.example_pinyin, kind: 'pinyin' },
          ],
        })
      }
      return blocks
    }
    case 'en_to_zh': {
      const blocks: DisplayBlock[] = [
        {
          role: 'word',
          lines: [{ text: card.answer_english, kind: 'english' }],
        },
      ]
      if (example) {
        blocks.push({
          role: 'example',
          lines: [{ text: card.example_english, kind: 'english' }],
        })
      }
      return blocks
    }
    case 'zh_to_en': {
      const blocks: DisplayBlock[] = [
        {
          role: 'word',
          lines: [{ text: card.answer_chinese, kind: 'chinese' }],
        },
      ]
      if (example) {
        blocks.push({
          role: 'example',
          lines: [{ text: card.example_chinese, kind: 'chinese' }],
        })
      }
      return blocks
    }
    default:
      return [
        {
          role: 'word',
          lines: [{ text: card.prompt, kind: 'english' }],
        },
      ]
  }
}

export function cardReveal(card: StudyCard): DisplayBlock[] {
  const example = hasExample(card)

  switch (card.mode) {
    case 'pinyin_to_en': {
      const blocks: DisplayBlock[] = [
        {
          role: 'word',
          lines: [{ text: card.answer_english, kind: 'english' }],
        },
      ]
      if (example) {
        blocks.push({
          role: 'example',
          lines: [{ text: card.example_english, kind: 'english' }],
        })
      }
      return blocks
    }
    case 'en_to_zh': {
      const blocks: DisplayBlock[] = [
        {
          role: 'word',
          lines: [
            { text: card.answer_chinese, kind: 'chinese' },
            { text: card.answer_pinyin, kind: 'pinyin' },
          ],
        },
      ]
      if (example) {
        blocks.push({
          role: 'example',
          lines: [
            { text: card.example_chinese, kind: 'chinese' },
            { text: card.example_pinyin, kind: 'pinyin' },
          ],
        })
      }
      return blocks
    }
    case 'zh_to_en': {
      const blocks: DisplayBlock[] = [
        {
          role: 'word',
          lines: [
            { text: card.answer_pinyin, kind: 'pinyin' },
            { text: card.answer_english, kind: 'english' },
          ],
        },
      ]
      if (example) {
        blocks.push({
          role: 'example',
          lines: [
            { text: card.example_pinyin, kind: 'pinyin' },
            { text: card.example_english, kind: 'english' },
          ],
        })
      }
      return blocks
    }
    default:
      return [
        {
          role: 'word',
          lines: [{ text: card.answer_english, kind: 'english' }],
        },
      ]
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
