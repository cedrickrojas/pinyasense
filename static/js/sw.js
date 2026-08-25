const CACHE_NAME = 'pinasense-v2';
const CORE_ASSETS = [
  '/',
  '/manifest.webmanifest',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/js/pwa.js',
  '/static/icons/pinya-icon.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // Never cache/serve page navigations (dashboard, login, etc.) from the SW cache.
  // These are session-dependent and change often (e.g. which section shows on load);
  // serving a stale cached copy caused the dashboard to reappear scrolled into an old
  // section after login/refresh even after the underlying page was fixed. Only static
  // assets (css/js/icons) below get the offline-friendly cache-and-fallback treatment.
  if (request.mode === 'navigate' || request.destination === 'document') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/'))
    );
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
        return response;
      })
      .catch(() =>
        caches.match(request).then((cached) => {
          if (cached) {
            return cached;
          }
          return caches.match('/');
        })
      )
  );
});
