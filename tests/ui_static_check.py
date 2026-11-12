"""No /static asset without a version, and the right cache headers, checked through nginx
(Playwright, dev venv only):
    .venv-dev/bin/python tests/ui_static_check.py https://waterscribe.robix
    .venv-dev/bin/python tests/ui_static_check.py http://127.0.0.1:5055 --no-headers   # preview, no nginx
Loads every tank page and Manage, opens each tab and the entry drawer, and records every /static
request plus every /static URL in the HTML and the manifest. Each must carry ?v=<10 hex> and load 200.
Headers: versioned /static immutable for a year, the same path unversioned short-lived, /sw.js and
the manifest no-cache. Read-only: non-GET requests are blocked."""
import re
import sys
from urllib.parse import urlparse, parse_qs, urljoin

from playwright.sync_api import sync_playwright

base = sys.argv[1].rstrip('/')
headers = '--no-headers' not in sys.argv
IMMUTABLE = 'public, max-age=31536000, immutable'
VERSION = re.compile(r'^[0-9a-f]{10}$')
failures, seen = [], {}


def check(name, cond, detail=''):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")
    if not cond:
        failures.append(name)


def versioned(url):
    return bool(VERSION.match(parse_qs(urlparse(url).query).get('v', [''])[0]))


def note(url, how):
    u = urlparse(urljoin(base + '/', url))
    if u.path.startswith('/static/') and u.netloc == urlparse(base).netloc:
        seen.setdefault(u.path + ('?' + u.query if u.query else ''), set()).add(how)


with sync_playwright() as p:
    b = p.chromium.launch()
    for label, vp, mob in (('desktop', {'width': 1280, 'height': 900}, False), ('iphone', {'width': 390, 'height': 844}, True)):
        ctx = b.new_context(viewport=vp, is_mobile=mob, has_touch=mob, ignore_https_errors=True)
        ctx.route('**/*', lambda r: r.continue_() if r.request.method in ('GET', 'HEAD') else r.abort())
        statuses = {}
        ctx.on('request', lambda r: note(r.url, 'requested'))
        ctx.on('response', lambda r: statuses.__setitem__(r.url, r.status))
        page = ctx.new_page()
        tanks = page.request.get(f'{base}/api/aquariums').json()
        ids = [t['id'] for t in (tanks if isinstance(tanks, list) else tanks.get('aquariums', []))]
        for path in [f'/?aquarium_id={i}' for i in ids] + ['/aquariums']:
            page.goto(base + path)
            page.wait_for_load_state('networkidle')
            if path.startswith('/?'):
                for tab in page.locator('.tab-btn').all():
                    tab.click()
                page.click('#log-btn')
                page.keyboard.press('Escape')
            for attr in page.evaluate("""[...document.querySelectorAll('[href],[src]')].map(e => e.getAttribute('href') || e.getAttribute('src'))"""):
                note(attr, 'linked')
            for m in re.findall(r'/static/[^"\'\s<>)]*', page.content()):
                note(m.replace('&amp;', '&'), 'in page')
        sw = page.evaluate("navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(rs => rs.map(r => (r.active || r.installing || r.waiting || {}).scriptURL)) : []")
        for u in sw:
            check(f'{label}: service worker at the fixed /sw.js', urlparse(u).path == '/sw.js' and not urlparse(u).query, u)
        man = page.locator('link[rel=manifest]').get_attribute('href')
        r = page.request.get(urljoin(base + '/', man))
        check(f'{label}: manifest served', r.ok and 'manifest' in r.headers.get('content-type', ''), f'{man} {r.status}')
        for icon in r.json().get('icons', []):
            note(icon['src'], 'manifest icon')
        print(f'== {label}: {len(ids)} tanks, service worker {sw or "not registered"}')
        bad_status = {u: s for u, s in statuses.items() if '/static/' in u and s != 200 and s != 304}
        check(f'{label}: every /static response 200', not bad_status, str(bad_status))
        ctx.close()

    # every URL seen must be versioned, and nginx must serve it
    ctx = b.new_context(ignore_https_errors=True)
    for url, how in sorted(seen.items()):
        r = ctx.request.get(base + url)
        print(f"    {'v' if versioned(url) else '-'} {r.status} {url}  [{', '.join(sorted(how))}]")
    unversioned = [u for u in seen if not versioned(u)]
    check('no /static URL without ?v=<hash>', seen and not unversioned, f'{len(seen)} URLs' if not unversioned else ', '.join(unversioned))
    check('every versioned URL loads through nginx', all(ctx.request.get(base + u).ok for u in seen))
    kinds = {h for hs in seen.values() for h in hs}
    check('covered requests, links and manifest icons', {'requested', 'linked', 'manifest icon'} <= kinds, str(sorted(kinds)))
    check('service worker is not a /static asset', not any(urlparse(u).path.endswith('sw.js') for u in seen))
    if headers:
        cc = lambda u: ctx.request.get(base + u).headers.get('cache-control', '')
        bad = {u: cc(u) for u in seen if cc(u) != IMMUTABLE}
        check(f'versioned /static: {IMMUTABLE}', not bad, str(bad))
        short = {}
        for path in {urlparse(u).path for u in seen}:
            v = cc(path)
            m = re.search(r'max-age=(\d+)', v)
            if 'immutable' in v or not m or int(m.group(1)) > 3600:
                short[path] = v
        check('unversioned /static: short max-age, not immutable', not short, str(short) if short else cc(urlparse(next(iter(seen))).path))
        for path in ('/sw.js', '/manifest.webmanifest'):
            check(f'{path}: no-cache', cc(path) == 'no-cache', cc(path))
    b.close()

print('FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED')
sys.exit(1 if failures else 0)
