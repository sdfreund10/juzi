/** Register the app-shell service worker (same-origin production builds only). */
export function registerServiceWorker (): void {
  if (!('serviceWorker' in navigator)) {
    return
  }
  // Skip under Vite HMR so stale SW caches do not fight the dev server.
  if (import.meta.env.DEV) {
    return
  }

  navigator.serviceWorker.register('/sw.js').catch(() => {
    // Installability still works without a controlling SW; ignore register failures.
  })
}
