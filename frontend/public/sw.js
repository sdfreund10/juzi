/* App-shell cache only. Never cache /api or /admin. */
const CACHE = 'juzi-shell-v2'

const PRECACHE = ['/site.webmanifest', '/favicon.svg']

function isApiOrAdmin(url) {
  return url.pathname.startsWith('/api') || url.pathname.startsWith('/admin')
}

function isShellAsset(url) {
  return (
    url.origin === self.location.origin &&
    (url.pathname.startsWith('/assets/') ||
      url.pathname.endsWith('.png') ||
      url.pathname.endsWith('.svg') ||
      url.pathname.endsWith('.webmanifest') ||
      url.pathname === '/' ||
      url.pathname === '/index.html')
  )
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') {
    return
  }

  const url = new URL(request.url)
  if (url.origin !== self.location.origin || isApiOrAdmin(url)) {
    return
  }

  if (!isShellAsset(url)) {
    return
  }

  // Navigations: network first, fall back to cached shell.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
.then(async (response) => {
          if (response.ok) {
            const copy = response.clone()
            const cache = await caches.open(CACHE)
            await cache.put('/', copy)
          }
          return response
        })
.catch(async () => (await caches.match('/')) ?? caches.match('/index.html')),
    )
    return
  }

  // Static assets: cache on first success (handles Vite hashed filenames).
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        return cached
      }
      return fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone()
          caches.open(CACHE).then((cache) => cache.put(request, copy))
        }
        return response
      })
    }),
  )
})
