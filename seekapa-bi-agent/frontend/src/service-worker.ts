/// <reference lib="WebWorker" />

// Define the service worker context
declare const self: ServiceWorkerGlobalScope

const CACHE_NAME = 'seekapa-bi-v1'
const RUNTIME_CACHE = 'seekapa-runtime-v1'

// Resources to cache on install
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json'
]

// Install event - cache core resources
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Pre-caching app shell')
        return cache.addAll(PRECACHE_URLS)
      })
      .then(() => {
        console.log('[SW] Installation completed')
        return self.skipWaiting()
      })
  )
})

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((cacheName) => {
            // Delete old caches
            return cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE
          })
          .map((cacheName) => {
            console.log('[SW] Deleting old cache:', cacheName)
            return caches.delete(cacheName)
          })
      )
    }).then(() => {
      console.log('[SW] Activation completed')
      return self.clients.claim()
    })
  )
})

// Fetch event - implement caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return
  }

  // Skip WebSocket connections
  if (request.url.includes('ws://') || request.url.includes('wss://')) {
    return
  }

  // Skip API calls (let them go to network)
  if (request.url.includes('/api/')) {
    return
  }

  event.respondWith(
    caches.match(request)
      .then((response) => {
        // Return cached version if available
        if (response) {
          console.log('[SW] Serving from cache:', request.url)
          return response
        }

        // Fetch from network and cache the response
        return fetch(request)
          .then((response) => {
            // Don't cache if not a valid response
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response
            }

            // Clone the response
            const responseToCache = response.clone()

            // Cache static assets and pages
            if (
              request.url.includes('.js') ||
              request.url.includes('.css') ||
              request.url.includes('.png') ||
              request.url.includes('.svg') ||
              request.url.includes('.woff') ||
              request.url.includes('.woff2') ||
              request.destination === 'document'
            ) {
              caches.open(RUNTIME_CACHE)
                .then((cache) => {
                  console.log('[SW] Caching new resource:', request.url)
                  cache.put(request, responseToCache)
                })
            }

            return response
          })
          .catch(() => {
            // If network fails, try to serve from cache
            if (request.destination === 'document') {
              return caches.match('/index.html').then(cachedResponse => cachedResponse || new Response('Offline'))
            }
            return new Response('Offline content not available', {
              status: 503,
              statusText: 'Service Unavailable'
            })
          })
      })
  )
})

export {}