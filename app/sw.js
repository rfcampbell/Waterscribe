// WaterScribe service worker. Served by the app at /sw.js: fixed URL, Cache-Control no-cache, scope /.
// BUILD is a hash over every /static file, filled in per request, so a deploy that changes any asset
// changes this script and the browser installs the new worker on the next page load.
//   pages, API, anything unversioned: not intercepted -> straight to the network, never cached here
//   versioned /static assets (?v=<content hash>): cache-first; the URL changes whenever the content does
const BUILD = '__BUILD__';
const CACHE = `ws-static-${BUILD}`;
const VERSIONED = /^[0-9a-f]{10}$/;

// take over at once: no page ever needs the old worker, because HTML is never served from here
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
    e.waitUntil((async () => {
        for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);   // incl. old 'waterscribe-v2'
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;
    if (!url.pathname.startsWith('/static/') || !VERSIONED.test(url.searchParams.get('v') || '')) return;
    e.respondWith((async () => {
        const cache = await caches.open(CACHE);
        const hit = await cache.match(e.request);
        if (hit) return hit;
        const resp = await fetch(e.request);
        if (resp.ok) await cache.put(e.request, resp.clone());
        return resp;
    })());
});
