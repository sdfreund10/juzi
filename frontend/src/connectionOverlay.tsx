import { useLayoutEffect, useRef, useState } from 'preact/hooks'
import { useAuth } from './auth'

export function ConnectionOverlay () {
  const { hasOfflineCache, enterOffline, retryConnection } = useAuth()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [retrying, setRetrying] = useState(false)

  useLayoutEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (!dialog.open) dialog.showModal()

    function keepOpen (event: Event) {
      event.preventDefault()
    }

    dialog.addEventListener('cancel', keepOpen)
    return () => {
      dialog.removeEventListener('cancel', keepOpen)
      if (dialog.open) dialog.close()
    }
  }, [])

  async function onRetry () {
    setRetrying(true)
    try {
      await retryConnection()
    } finally {
      setRetrying(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      class='connection-overlay'
      aria-labelledby='connection-overlay-title'
    >
      <div class='connection-overlay-panel'>
        <h2 id='connection-overlay-title' class='title'>
          Cannot connect to server
        </h2>
        <p class='lede'>
          juzi cannot reach the server right now.
        </p>
        <div class='picker-actions connection-overlay-actions'>
          <button
            type='button'
            class='cta'
            disabled={retrying}
            onClick={() => {
              onRetry().catch(() => {})
            }}
          >
            {retrying ? 'Retrying…' : 'Retry'}
          </button>
          <button
            type='button'
            class='cta ghost'
            disabled={!hasOfflineCache || retrying}
            onClick={enterOffline}
          >
            Continue Offline
          </button>
        </div>
      </div>
    </dialog>
  )
}
