// CBODS Service Worker
// Provides offline support for donor-facing pages and queues mutations for background sync.

const CACHE_NAME = 'cbods-v1';
const STATIC_CACHE_NAME = 'cbods-static-v1';
const MUTATION_CACHE_NAME = 'cbods-mutations-v1';

// Assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/static/vendor/bootstrap.min.css',
  '/static/css/cbods.css',
  '/static/vendor/bootstrap.bundle.min.js',
  '/static/vendor/htmx.min.js',
  '/static/js/theme.js',
  '/static/js/session-timeout.js',
  '/static/favicon.svg',
];

// Pages to cache for offline viewing
const OFFLINE_PAGES = [
  '/donors/',
  '/donors/profile/',
  '/donors/appointments/',
  '/donors/donation-sites/',
];

// Install: cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(name => name !== STATIC_CACHE_NAME && name !== MUTATION_CACHE_NAME)
          .map(name => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch: network-first for HTML, cache-first for static assets
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests for caching (they'll be handled by mutation queue)
  if (request.method !== 'GET') {
    // Queue mutations for background sync
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method)) {
      event.respondWith(handleMutation(request));
    }
    return;
  }

  // HTML pages: network-first with offline fallback
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const cloned = response.clone();
            caches.open(STATIC_CACHE_NAME).then(cache => cache.put(request, cloned));
          }
          return response;
        })
        .catch(() => caches.match(request))
        .catch(() => caches.match('/offline.html'))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(response => {
        if (response.ok) {
          const cloned = response.clone();
          caches.open(STATIC_CACHE_NAME).then(cache => cache.put(request, cloned));
        }
        return response;
      });
    })
  );
});

// Handle mutations (POST/PUT/PATCH/DELETE) - queue for background sync
async function handleMutation(request) {
  try {
    // Try network first
    const response = await fetch(request);
    return response;
  } catch (error) {
    // Network failed - queue for later
    await queueMutation(request);
    // Return a synthetic response indicating queued
    return new Response(
      JSON.stringify({ queued: true, message: 'Request queued for background sync' }),
      {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }
}

// Queue a mutation for background sync
async function queueMutation(request) {
  const cache = await caches.open(MUTATION_CACHE_NAME);
  const body = await request.clone().text();
  const mutation = {
    url: request.url,
    method: request.method,
    headers: [...request.headers.entries()],
    body,
    timestamp: Date.now(),
  };
  // Store with a unique key
  const key = `mutation-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  await cache.put(key, new Response(JSON.stringify(mutation), {
    headers: { 'Content-Type': 'application/json' },
  }));
  // Register background sync
  if ('serviceWorker' in navigator && 'sync' in self.registration) {
    await self.registration.sync.register('replay-mutations');
  }
}

// Background sync: replay queued mutations
self.addEventListener('sync', event => {
  if (event.tag === 'replay-mutations') {
    event.waitUntil(replayMutations());
  }
});

async function replayMutations() {
  const cache = await caches.open(MUTATION_CACHE_NAME);
  const keys = await cache.keys();
  const mutationKeys = keys.filter(req => req.url.includes('mutation-'));

  for (const key of mutationKeys) {
    try {
      const response = await cache.match(key);
      const mutation = await response.json();

      // Reconstruct request
      const request = new Request(mutation.url, {
        method: mutation.method,
        headers: mutation.headers,
        body: mutation.body,
      });

      // Try to send
      const result = await fetch(request);

      if (result.ok) {
        // Success - remove from queue
        await cache.delete(key);
        // Notify client
        self.clients.matchAll().then(clients => {
          clients.forEach(client => client.postMessage({
            type: 'mutation-success',
            key: key.url,
          }));
        });
      } else {
        // Server error - keep in queue for retry
        console.warn('Mutation failed, will retry:', mutation.url, result.status);
      }
    } catch (error) {
      // Network error - keep in queue
      console.warn('Mutation network error, will retry:', error);
    }
  }
}

// Push notification handling
self.addEventListener('push', event => {
  if (!event.data) return;

  const data = event.data.json();
  const options = {
    body: data.body,
    icon: '/static/favicon.svg',
    badge: '/static/favicon.svg',
    vibrate: [200, 100, 200],
    data: data.data || {},
    actions: data.actions || [],
    requireInteraction: data.requireInteraction || false,
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const data = event.notification.data;

  if (event.action === 'open' || !event.action) {
    // Open the relevant page
    const url = data.url || '/donors/';
    event.waitUntil(
      self.clients.matchAll({ type: 'window' }).then(clients => {
        for (const client of clients) {
          if (client.url === url && 'focus' in client) {
            return client.focus();
          }
        }
        return self.clients.openWindow(url);
      })
    );
  }
});

// Message handling from clients
self.addEventListener('message', event => {
  if (event.data?.type === 'skipWaiting') {
    self.skipWaiting();
  }
});