const CACHE_NAME = 'stock-dashboard-v1';
const urlsToCache = [
  './',
  './index.html',
  './manifest.json'
];

// 설치 단계: 캐싱
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

// 패치 단계: 네트워크 우선 (실시간 증시 데이터이므로 네트워크를 항상 우선시함)
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
