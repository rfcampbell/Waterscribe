"""No /static asset without a version, checked through nginx (Playwright, dev venv only):
    .venv-dev/bin/python tests/ui_static_check.py https://waterscribe.robix
Loads every tank page and Manage, opens each tab and the entry drawer, lets the page register its
service worker, and records every /static request plus every /static URL in the HTML and the manifest.
Each must carry ?v=<10 hex> and load 200. Read-only: non-GET requests are blocked."""
import re
import sys
from urllib.parse import urlparse, parse_qs, urljoin

from playwright.sync_api import sync_playwright

base = sys.argv[1].rstrip('/')
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
        # registration needs a trusted certificate, which robix's mkcert CA isn't to headless Chromium;
        # the register() call still fetches the script, which is what gets checked
        sw = page.evaluate("navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(rs => rs.map(r => (r.active || r.installing || r.waiting || {}).scriptURL)) : []")
        for u in sw:
            note(u, 'service worker')
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
    # the page only registers its service worker on a secure origin (https, or localhost)
    secure = base.startswith('https://') or urlparse(base).hostname in ('127.0.0.1', 'localhost')
    sw_script = [u for u, hs in seen.items() if urlparse(u).path == '/static/sw.js' and ('requested' in hs or not secure)]
    check('covered requests, links, manifest icons and the service worker script',
          {'requested', 'linked', 'manifest icon'} <= kinds and sw_script,
          f"{sorted(kinds)}; sw.js {'requested' if secure else 'in page (http: not registered)'}: {sw_script}")
    b.close()

print('FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED')
sys.exit(1 if failures else 0)
