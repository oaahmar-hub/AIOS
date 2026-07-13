// AIOS service worker — KILL SWITCH.
// A previous cached build could get stuck and serve users a blank/broken shell
// that survived normal refreshes. This version deliberately caches NOTHING:
// on activate it deletes every cache and unregisters itself, then reloads any
// open windows so every device drops the poison and loads fresh from the
// network. After this runs once, there is no service worker caching at all —
// the app is always fetched live.
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    } catch (e) {}
    try { await self.registration.unregister(); } catch (e) {}
    try {
      const wins = await self.clients.matchAll({ type: "window" });
      for (const w of wins) {
        try { w.navigate(w.url); } catch (e) {}
      }
    } catch (e) {}
  })());
});

// Never serve from cache — always go straight to the network.
self.addEventListener("fetch", event => {
  event.respondWith(fetch(event.request).catch(() => new Response("", { status: 504 })));
});
