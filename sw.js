// Service Worker PNKB Forest Watch - Mode Hors-Ligne
const CACHE_NAME = 'pnkb-cache-v2';

const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './dashboard.html',
  './data.js',
  './data/alerts.js',
  './data/pnkb_boundary.geojson',
  './data/chimanuka.jpg',
  './data/gorillon.jpg',
  './data/foret.jpg',
  './data/cascade.jpg',
  'https://cdn.tailwindcss.com',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://cdn.jsdelivr.net/npm/chart.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Stratégie Réseau d'abord, secours sur Cache si hors-ligne
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
