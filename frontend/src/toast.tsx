import { useEffect, useState } from 'preact/hooks'

type ToastHandler = (message: string) => void

let handler: ToastHandler | null = null

export function setToastHandler(next: ToastHandler | null): void {
  handler = next
}

export function showToast(message: string): void {
  handler?.(message)
}

const TOAST_MS = 4000

export function ToastHost() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    setToastHandler((next) => setMessage(next))
    return () => setToastHandler(null)
  }, [])

  useEffect(() => {
    if (!message) return
    const id = window.setTimeout(() => setMessage(null), TOAST_MS)
    return () => window.clearTimeout(id)
  }, [message])

  if (!message) return null

  return (
    <div class="toast" role="status" aria-live="polite">
      {message}
    </div>
  )
}
