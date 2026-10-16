import { brandMarkSrc } from './brandMark.ts'

export function Brand () {
  return (
    <header class='masthead'>
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
    </header>
  )
}
