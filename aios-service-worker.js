const AIOS_CACHE = "aios-presence-v86";
const AIOS_SHELL = [
  "/AIOS-WEBSITE.html",
  "/aios.webmanifest",
  "/offline.html",
  "/assets/aios-icon-192.png",
  "/assets/aios-icon-512.png",
  "/assets/aios-icon-maskable-512.png"
];
const AIOS_PROTECTED_PATHS = new Set([
  "/AIOS-DASHBOARD.html",
  "/AIOS-MOBILE-APP.html",
  "/AIOS-RUNTIME-STATUS.html"
]);

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(AIOS_CACHE)
      .then(cache => cache.addAll(AIOS_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== AIOS_CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok && !AIOS_PROTECTED_PATHS.has(url.pathname)) {
            const copy = response.clone();
            caches.open(AIOS_CACHE).then(cache => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request).then(cached => cached || caches.match("/offline.html")))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => cached || fetch(request).then(response => {
      if (
        response.ok &&
        !AIOS_PROTECTED_PATHS.has(url.pathname) &&
        !url.pathname.startsWith("/assets/aios-eye-cinematic-loop-")
      ) {
        const copy = response.clone();
        caches.open(AIOS_CACHE).then(cache => cache.put(request, copy));
      }
      return response;
    }))
  );
});
