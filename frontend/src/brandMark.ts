/** Filled mark in production; outline mark for development builds. */
export const brandMarkSrc =
  import.meta.env.MODE === 'development' ? '/favicon-dev.svg' : '/favicon.svg'
