import type { ComponentChildren } from 'preact'
import { brandMarkSrc } from './brandMark.ts'

export function Brand ({ end }: { end?: ComponentChildren } = {}) {
  return (
    <header class={`masthead${end ? ' masthead-split' : ''}`}>
      <p class='brand'>
        <img
          class='brand-mark'
          src={brandMarkSrc}
          alt=''
          width='28'
          height='28'
        />
        juzi
      </p>
      {end != null ? <div class='masthead-end'>{end}</div> : null}
    </header>
  )
}
