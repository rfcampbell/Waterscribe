"""Service worker: a deploy reaches a page the old worker controls, with no cache clearing (Playwright,
dev venv only). Needs a LOCAL preview serving APP_DIR, because it "deploys" by changing a static file:
    .venv-dev/bin/python tests/ui_sw_check.py http://127.0.0.1:5055 --app-dir . --tank 4
127.0.0.1 counts as a secure origin, so the worker registers. The file is restored afterwards.
Read-only towards the app: non-GET requests are blocked."""
import argparse
import re
import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('base')
ap.add_argument('--app-dir', required=True)
ap.add_argument('--tank', type=int, required=True)
args = ap.parse_args()
ASSET = Path(args.app_dir, 'app', 'static', 'js', 'mainchart.js')
failures = []

# the worker that shipped before this change (registered from /static/sw.js, scope /static/)
LEGACY_SW = """const CACHE_NAME = 'waterscribe-v2';
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(['/']))); self.skipWaiting(); });
self.addEventListener('activate', e => { self.clients.claim(); });
self.addEventListener('fetch', e => { e.respondWith(fetch(e.request).catch(() => caches.match(e.request))); });"""


def check(name, cond, detail=''):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")
    if not cond:
        failures.append(name)


STATE_JS = """(async () => {
    const rs = await navigator.serviceWorker.getRegistrations();
    const keys = await caches.keys();
    return { regs: rs.map(r => [new URL(r.scope).pathname, (r.active || r.waiting || r.installing || {}).scriptURL]),
             controller: navigator.serviceWorker.controller && navigator.serviceWorker.controller.scriptURL,
             caches: keys, cached: keys.length ? (await (await caches.open(keys[0])).keys()).map(r => r.url) : [],
             build: (await (await fetch('/sw.js', { cache: 'no-store' })).text()).match(/const BUILD = '([0-9a-f]+)'/)[1] };
})()"""


def wait_for(page, pred, what, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        st = page.evaluate(STATE_JS)
        if pred(st):
            return st
        page.wait_for_timeout(250)
    print(f'      timed out waiting for {what}: {st}')
    return st


original = ASSET.read_bytes()
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context()
    ctx.route('**/*', lambda r: r.continue_() if r.request.method in ('GET', 'HEAD') else r.abort())
    page = ctx.new_page()
    try:
        # 0. a browser that still has the legacy worker and its precached '/'
        ctx.route('**/static/legacy-setup', lambda r: r.fulfill(content_type='text/html', body="""<script>
            navigator.serviceWorker.register('/static/sw.js', { scope: '/static/' }).then(r => document.title = 'registered');
        </script>"""))
        ctx.route('**/static/sw.js', lambda r: r.fulfill(content_type='text/javascript', body=LEGACY_SW))
        page.goto(f'{args.base}/static/legacy-setup')
        page.wait_for_function("document.title === 'registered'")
        st = wait_for(page, lambda s: 'waterscribe-v2' in s['caches'], 'legacy cache')
        check('setup: legacy worker registered with its cache', ['/static/', f'{args.base}/static/sw.js'] in st['regs'] and 'waterscribe-v2' in st['caches'], str(st['regs']))
        ctx.unroute('**/static/sw.js')

        # 1. first visit: the new worker takes over, the legacy one and its cache are gone
        url = f'{args.base}/?aquarium_id={args.tank}'
        page.goto(url)
        only_current = lambda s: set(s['caches']) <= {f"ws-static-{s['build']}"}   # a build's cache appears on first use
        st = wait_for(page, lambda s: s['controller'] and s['regs'] == [['/', f'{args.base}/sw.js']] and only_current(s),
                      'new worker in control')
        b1 = st['build']
        check('new worker at the fixed /sw.js controls the page', st['controller'] == f'{args.base}/sw.js', str(st['controller']))
        check('legacy /static/ registration removed', st['regs'] == [['/', f'{args.base}/sw.js']], str(st['regs']))
        check('old caches deleted on activate (legacy waterscribe-v2 gone)', only_current(st), str(st['caches']))
        sw = page.request.get(f'{args.base}/sw.js')
        check('/sw.js served no-cache, unversioned', sw.headers.get('cache-control') == 'no-cache', sw.headers.get('cache-control'))

        # 2. strategy: HTML from the network, versioned assets cache-first
        responses = []
        page.on('response', lambda r: responses.append(r))
        page.reload(); page.wait_for_load_state('networkidle')
        nav = next(r for r in responses if r.url == url)
        js = [r for r in responses if '/static/js/mainchart.js?v=' in r.url]
        check('HTML not served by the worker', not nav.from_service_worker)
        check('versioned asset served cache-first by the worker', js and js[0].from_service_worker, js[0].url if js else 'not loaded')
        st = page.evaluate(STATE_JS)
        check('only versioned /static URLs in the cache', st['cached'] and all(re.search(r'/static/.+\?v=[0-9a-f]{10}$', u) for u in st['cached']),
              str(st['cached']))
        old_src = page.get_attribute('script[src*="mainchart.js"]', 'src')

        # 3. deploy while the old worker controls the page
        marker = uuid.uuid4().hex[:8]
        ASSET.write_bytes(original + f"\n;window.__deployMarker = '{marker}';\n".encode())
        check('page still controlled by the old build before reload', page.evaluate(STATE_JS)['caches'] == [f'ws-static-{b1}'])
        responses.clear()
        page.reload(); page.wait_for_load_state('networkidle')
        new_src = page.get_attribute('script[src*="mainchart.js"]', 'src')
        check('one reload: new HTML references the new asset version', new_src != old_src, f'{old_src} -> {new_src}')
        check('one reload: new code runs, no cache clear', page.evaluate('window.__deployMarker') == marker,
              str(page.evaluate('window.__deployMarker')))
        st = wait_for(page, lambda s: s['build'] != b1 and only_current(s), 'new build activated')
        check('new worker activated, old build cache deleted', st['build'] != b1 and only_current(st),
              f"{b1} -> {st['build']}, caches {st['caches']}")
        check('new worker controls the page', st['controller'] == f'{args.base}/sw.js')
        responses.clear()
        page.reload(); page.wait_for_load_state('networkidle')
        st = page.evaluate(STATE_JS)
        check('next load: new asset cached under the new build only', st['caches'] == [f"ws-static-{st['build']}"]
              and any(new_src in u for u in st['cached']) and not any(old_src in u for u in st['cached']), f"{st['caches']} {st['cached']}")
    finally:
        ASSET.write_bytes(original)
        b.close()
check('asset restored', ASSET.read_bytes() == original)
print('FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED')
sys.exit(1 if failures else 0)
