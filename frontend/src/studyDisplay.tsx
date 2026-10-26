import {
  highlightHeadword,
  type DisplayBlock,
  type DisplayLine
} from './studyCard'

function lineClass (
  line: DisplayLine,
  face: 'prompt' | 'answer',
  blockRole: DisplayBlock['role']
): string {
  const parts = [
    face === 'prompt' ? 'prompt-line' : 'answer-line',
    line.kind
  ]
  if (line.kind === 'chinese') parts.push('zh')
  if (blockRole === 'example') parts.push('example')
  return parts.join(' ')
}

function LineText ({
  line,
  blockRole,
  headword
}: {
  line: DisplayLine
  blockRole: DisplayBlock['role']
  headword: string
}) {
  if (blockRole !== 'example' || line.kind !== 'chinese') {
    return line.text
  }
  return highlightHeadword(line.text, headword).map((segment, index) =>
    segment.focus
      ? (
        <span key={`${index}-${segment.text}`} class='example-focus'>
          {segment.text}
        </span>
        )
      : (
        <span key={`${index}-${segment.text}`}>{segment.text}</span>
        )
  )
}

export function DisplayBlocks ({
  blocks,
  face,
  headword
}: {
  blocks: DisplayBlock[]
  face: 'prompt' | 'answer'
  headword: string
}) {
  return (
    <div
      class={
        face === 'prompt' ? 'prompt-block' : 'answer study-answer-enter'
      }
    >
      {blocks.map((block) => {
        const paired =
          block.role === 'word' &&
          block.lines.length === 2 &&
          block.lines[0]?.kind === 'chinese' &&
          block.lines[1]?.kind === 'pinyin'
        const linesBody = block.lines.map((line) => (
          <p
            key={`${block.role}-${line.kind}-${line.text}`}
            class={lineClass(line, face, block.role)}
          >
            <LineText
              line={line}
              blockRole={block.role}
              headword={headword}
            />
          </p>
        ))
        return (
          <div
            key={`${block.role}-${block.lines.map((l) => l.text).join('|')}`}
            class={`card-block card-block-${block.role}`}
          >
            {paired ? <div class='prompt-pair'>{linesBody}</div> : linesBody}
          </div>
        )
      })}
    </div>
  )
}
