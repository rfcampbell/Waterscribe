"""Browser check for the entry drawer and its tank-bound draft (Playwright, dev venv only):
    .venv-dev/bin/python tests/ui_drawer_check.py http://127.0.0.1:5055 --tank 4 --other 5 [--shots DIR]
Writes nothing: readings POSTs are intercepted, recorded and answered with a fake success."""
import argparse
import re
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('base')
ap.add_argument('--tank', type=int, required=True)
ap.add_argument('--other', type=int, required=True)
ap.add_argument('--shots')
args = ap.parse_args()

failures = []


def tank_of(url):
    return int(parse_qs(urlparse(url).query).get('aquarium_id', ['0'])[0])


def check(name, cond, detail=''):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")
    if not cond:
        failures.append(name)


def run(p, label, viewport, mobile):
    print(f'== {label}')
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    errors, posts, dialogs = [], [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
    answer = {'accept': False}

    def on_dialog(d):
        dialogs.append((d.type, d.message))
        d.accept() if answer['accept'] else d.dismiss()
    page.on('dialog', on_dialog)

    def on_post(route):
        if route.request.method != 'POST':
            return route.continue_()
        posts.append(route.request.url)
        route.fulfill(json={'success': True})
    blocked = []

    def block_writes(route):   # safety net: nothing but the faked readings POST may leave the browser
        if route.request.method in ('GET', 'HEAD'):
            return route.continue_()
        blocked.append(f'{route.request.method} {route.request.url}')
        route.abort()
    page.route('**/*', block_writes)
    page.route(re.compile(r'/api/aquarium/\d+/readings'), on_post)   # registered last, so matched first

    def shot(name):
        if args.shots:
            page.screenshot(path=f'{args.shots}/p4-{label}-{name}.png')

    tank_url = f'{args.base}/?aquarium_id={args.tank}'
    page.goto(tank_url)
    drawer = page.locator('#entry-drawer')
    pending = lambda: page.evaluate('pendingCount()')
    tank_methods = page.evaluate('TANK_METHODS')

    # open: time is now, methods are this tank's own
    page.click('#log-btn')
    check('drawer opens', drawer.evaluate('d => d.open'))
    now = datetime.now()
    when = page.input_value('#readings-date') + ' ' + page.input_value('#readings-time')
    check('prefilled with current time', when == now.strftime('%Y-%m-%d %H:%M'), when)
    param = next(iter(tank_methods), None)
    if param:
        page.evaluate(f"toggleGroup('{param}', false)")
        got = page.input_value(f'.pgroup[data-param="{param}"] .r-method')
        check(f"{param} method is this tank's last", got == tank_methods[param], got)
    shot('drawer')

    # type a draft, close: it survives and is counted
    page.evaluate("toggleGroup('kh', false)")
    page.fill('.pgroup[data-param="kh"] .r-value', '4.5')
    page.keyboard.press('Escape')
    check('Esc closes', not drawer.evaluate('d => d.open'))
    check('button counts the draft', 'unsaved' in page.text_content('#log-btn'), page.text_content('#log-btn'))
    shot('closed-draft')

    # every way off the page asks first; saying no keeps tank and draft
    other_pill = f'.pill[href*="aquarium_id={args.other}"]'
    for name, sel in [('tank pill', other_pill), ('Manage link', 'a.btn-mini'), ('logo', 'a.logo'), ('+ pill', '.pill-add')]:
        n = len(dialogs)
        page.click(sel)
        page.wait_for_timeout(300)
        asked = len(dialogs) == n + 1 and dialogs[-1][0] == 'confirm'
        check(f'{name}: warns', asked, dialogs[-1][1] if asked else 'no dialog')
        check(f'{name}: dismiss keeps tank + draft',
              tank_of(page.url) == args.tank and '#' not in page.url and pending() == 1, f'{page.url} pending={pending()}')

    # a draft can't save anywhere else: retarget the form, then submit
    page.evaluate(f"document.getElementById('readings-form').dataset.aquariumId = '{args.other}'")
    page.click('#log-btn')
    page.click('.drawer-foot .btn-primary')
    page.wait_for_timeout(300)
    check('retargeted form refuses to save', not posts and dialogs and 'another tank' in dialogs[-1][1],
          f'posts={posts}')
    page.evaluate(f"document.getElementById('readings-form').dataset.aquariumId = '{args.tank}'")
    page.keyboard.press('Escape')

    # back/close/typed URL: beforeunload
    n = len(dialogs)
    try:
        page.goto(f'{args.base}/manage-aquariums', timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(300)
    check('typed URL / back warns (beforeunload)', any(t == 'beforeunload' for t, _ in dialogs[n:]),
          str([t for t, _ in dialogs[n:]]))
    check('dismiss keeps the page', tank_of(page.url) == args.tank and pending() == 1, page.url)

    # say yes on a pill: the other tank starts empty, and back doesn't resurrect the draft
    page.click('#log-btn')
    page.fill('.pgroup[data-param="kh"] .r-method', 'DISCARDED KIT')   # an edited method must not come back either
    page.keyboard.press('Escape')
    answer['accept'] = True
    page.click(other_pill)
    page.wait_for_url(lambda u: tank_of(u) == args.other)
    check('accept switches tank', tank_of(page.url) == args.other)
    page.click('#log-btn')
    check('other tank: no draft', pending() == 0 and page.input_value('.pgroup[data-param="kh"] .r-value') == '')
    check('other tank: no unsaved count', 'unsaved' not in page.text_content('#log-btn'))
    check('other tank: form bound to it', page.evaluate("+document.getElementById('readings-form').dataset.aquariumId") == args.other)
    shot('other-tank')
    page.keyboard.press('Escape')
    page.go_back()
    page.wait_for_url(lambda u: tank_of(u) == args.tank)
    page.wait_for_load_state()
    kh_method = page.input_value('.pgroup[data-param="kh"] .r-method')
    check('back to first tank: discarded draft stays gone', pending() == 0 and kh_method != 'DISCARDED KIT',
          f'pending={pending()} kh method={kh_method!r}')

    # a real save posts to this tank only, and doesn't warn on its own reload
    answer['accept'] = False
    page.click('#log-btn')
    page.evaluate("toggleGroup('kh', false)")
    page.fill('.pgroup[data-param="kh"] .r-value', '4.6')
    n = len(dialogs)
    with page.expect_navigation():
        page.click('.drawer-foot .btn-primary')
    check('save posts to this tank', posts == [f'{args.base}/api/aquarium/{args.tank}/readings'], str(posts))
    check('save reload asks nothing', len(dialogs) == n, str(dialogs[n:]))

    check('no other writes attempted', not blocked, '; '.join(blocked))
    check('no page errors', not errors, '; '.join(errors[:3]))
    browser.close()


with sync_playwright() as p:
    run(p, 'desktop', {'width': 1280, 'height': 900}, False)
    run(p, 'iphone', {'width': 390, 'height': 844}, True)

print('FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED')
sys.exit(1 if failures else 0)
