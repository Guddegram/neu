// Service Worker: macht Majma installierbar und offline nutzbar.
// Strategie „erst Netz, dann Speicher“: Online gibt es immer die neueste Version,
// offline die zuletzt geladene.

const CACHE = 'majma-v1';
const SHELL = [
  './',
  './app/',
  './css/site.css',
  './css/app.css',
  './js/site.js',
  './js/data.js',
  './js/prayer.js',
  './js/icons.js',
  './js/app/main.js',
  './js/app/views.js',
  './js/app/install.js',
  './assets/logo.png',
  './assets/logo-mark.png',
  './assets/bg-dark.jpg',
  './assets/bg-light.jpg',
  './assets/icon-192.png',
  './assets/icon-rounded.png',
  './manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;
  const isFont = url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';
  if (!sameOrigin && !isFont) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok || res.type === 'opaque') {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true })
        .then((hit) => hit || (req.mode === 'navigate' ? caches.match('./app/') : Response.error()))),
  );
});
