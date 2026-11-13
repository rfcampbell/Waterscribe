"""Browser check: nothing renders outside a tile, however long its text (Playwright, dev venv only):
    .venv-dev/bin/python tests/ui_tile_overflow_check.py http://127.0.0.1:5055 --tank 4 [--engine webkit] [--shots DIR]
Read-only: non-GET requests are blocked. Real tiles are checked for a full-text title on each detail line,
then every tile's detail line, label and stale message get very long text (spaced, and one unbreakable
token) and each descendant's box must stay inside its tile, the tile inside its grid column."""
import argparse
import sys

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('base')
ap.add_argument('--tank', type=int, required=True)
ap.add_argument('--engine', default='chromium', choices=['chromium', 'webkit'])
ap.add_argument('--shots')
args = ap.parse_args()
failures = []

NOTE = ('Raised from 30 after a 0.49 peak pH drop (degassed 7.65, tank 7.16). Approximate count; '
        'needle valve hard to set finer than ~10 bubbles. ') * 3
TOKEN = 'AperaPH60meterRecalibratedAfterDrift' * 8   # no break opportunities (no spaces or hyphens)


def check(name, cond, detail=''):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")
    if not cond:
        failures.append(name)


TITLES_JS = """() => [...document.querySelectorAll('#tiles .tile-sub')].filter(s => s.textContent.trim())
    .map(s => ({ key: s.closest('.tile').dataset.key, text: s.textContent.replace(/\\s+/g, ' ').trim(),
                 title: (s.getAttribute('title') || '').replace(/\\s+/g, ' ').trim(), pairing: s.classList.contains('pairing') }))"""

INJECT_JS = """([note, token]) => {
    const ts = [...document.querySelectorAll('#tiles .tile')];
    ts.forEach((t, i) => {
        const long = i % 2 ? token : note;
        t.querySelectorAll('.tile-sub').forEach(s => { s.textContent = long; s.title = long; });
        t.querySelector('.tile-label').textContent = long;
        let m = t.querySelector('.tile-message');
        if (!m && i === 0) {   // the stale CO2 tile's message, as the server renders it
            m = document.createElement('div'); m.className = 'tile-value tile-message'; t.querySelector('.tile-head').after(m); }
        if (m) m.textContent = token;
        const g = t.querySelector('.tile-target'); if (g) g.textContent = 'target ' + token;
    });
    return ts.length;
}"""

GEOM_JS = """() => {
    const grid = document.getElementById('tiles'), cols = getComputedStyle(grid).gridTemplateColumns.split(' ').map(parseFloat);
    const out = [], subs = [];
    for (const t of grid.querySelectorAll('.tile')) {
        const r = t.getBoundingClientRect();
        if (Math.abs(r.width - cols[0]) > 1) out.push(`${t.dataset.key}: tile ${r.width.toFixed(0)}px vs column ${cols[0].toFixed(0)}px`);
        // Measure element boxes AND the glyphs of every text node: text overflowing its own box is not
        // an element, so element boxes alone miss it. What renders is the part inside every clipping ancestor.
        const items = [];
        for (const e of t.querySelectorAll('*')) items.push([e, [e.getBoundingClientRect()], e]);
        const w = document.createTreeWalker(t, NodeFilter.SHOW_TEXT);
        for (let n; (n = w.nextNode());) {
            if (!n.textContent.trim()) continue;
            const rg = document.createRange(); rg.selectNodeContents(n);
            items.push([n, [...rg.getClientRects()], n.parentElement]);
        }
        for (const [node, rects, from] of items) for (const b of rects) {
            if (!b.width || !b.height) continue;
            let box = { l: b.left, r: b.right, t: b.top, b: b.bottom };
            for (let a = node === from ? from.parentElement : from; a && a !== t.parentElement; a = a.parentElement) {
                const cs = getComputedStyle(a);
                if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
                    const c = a.getBoundingClientRect();
                    box = { l: Math.max(box.l, c.left), r: Math.min(box.r, c.right), t: Math.max(box.t, c.top), b: Math.min(box.b, c.bottom) };
                }
            }
            if (box.r <= box.l || box.b <= box.t) continue;
            if (box.l < r.left - 0.5 || box.r > r.right + 0.5 || box.t < r.top - 0.5 || box.b > r.bottom + 0.5) {
                const what = node.nodeType === 3 ? `text in .${from.className}` : `.${(node.className.baseVal ?? node.className) || node.tagName}`;
                out.push(`${t.dataset.key}: ${what} renders ${Math.round(Math.max(box.r - r.right, r.left - box.l, box.b - r.bottom))}px outside`);
            }
        }
        for (const s of t.querySelectorAll('.tile-sub')) {
            const lh = parseFloat(getComputedStyle(s).lineHeight);
            subs.push({ key: t.dataset.key, lines: Math.round(s.getBoundingClientRect().height / lh), clamped: s.scrollHeight > s.clientHeight + 1 });
        }
    }
    return { out, subs, hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth };
}"""


def run(b, label, viewport, mobile):
    print(f'== {args.engine} {label}')
    ctx = b.new_context(viewport=viewport, is_mobile=mobile and args.engine == 'chromium', has_touch=mobile,
                        device_scale_factor=2 if mobile else 1, service_workers='block')   # SW fetches bypass page.route in WebKit
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('**/*', lambda r: r.continue_() if r.request.method in ('GET', 'HEAD') else r.abort())

    def series(route):   # one very long note on the newest point, for the chart tooltip
        data = route.fetch().json()
        if data['points']:
            data['points'][-1]['notes'] = NOTE + TOKEN
        route.fulfill(json=data)
    page.route(f'**/api/aquarium/{args.tank}/series?key=*', series)
    page.goto(f'{args.base}/?aquarium_id={args.tank}')
    page.wait_for_selector('#tiles .tile')

    real = page.evaluate(TITLES_JS)
    bad = [s['key'] for s in real if not (s['title'] and (s['title'] == s['text'] or s['pairing']))]
    check(f'{label}: real detail lines carry a full-text title', real and not bad, f"{len(real)} lines; missing/different: {bad}")
    bubble = next((s for s in real if s['key'] == 'co2_bubble_rate'), None)
    if bubble:
        check(f'{label}: bubble-rate note is in its title', len(bubble['title']) == len(bubble['text']), bubble['title'][:50])
    if args.shots:
        page.locator('#tiles').screenshot(path=f'{args.shots}/after-{label}-tiles-real.png')

    n = page.evaluate(INJECT_JS, [NOTE, TOKEN])
    page.wait_for_timeout(100)
    g = page.evaluate(GEOM_JS)
    check(f'{label}: nothing renders outside any of {n} tiles', not g['out'], '; '.join(g['out'][:4]))
    check(f'{label}: no horizontal page scroll', not g['hscroll'])
    over = [s['key'] for s in g['subs'] if s['lines'] > 2]
    check(f'{label}: long detail lines are at most 2 lines', not over, str(over))
    wrapped = [s for s in g['subs'] if s['lines'] == 2 and s['clamped']]
    check(f'{label}: long detail lines wrap to 2 lines and clamp', len(wrapped) == len(g['subs']),
          f"{len(wrapped)}/{len(g['subs'])} wrapped+clamped")
    check(f'{label}: clamp ends in an ellipsis (-webkit-line-clamp)', page.evaluate(
        "[...document.querySelectorAll('#tiles .tile-sub')].every(s => getComputedStyle(s).webkitLineClamp === '2')"))
    if args.shots:
        page.locator('#tiles').screenshot(path=f'{args.shots}/after-{label}-tiles-long-text.png')

    # chart tooltip: full note, inside the chart box
    first = page.locator('#tiles .tile').first.get_attribute('data-key')
    with page.expect_response(lambda r: '/series?key=' in r.url):   # else the reload hides the tip after we scrub
        page.click(f'#tiles .tile[data-key="{first}"]')
    page.wait_for_function('MainChart._state.chart && MainChart._state.data && MainChart._state.key === %r' % first)
    page.wait_for_timeout(150)
    page.evaluate("""(() => { const S = MainChart._state, pts = S.chart.data.datasets.flatMap(d => d.data).filter(d => !d.synthetic);
        const p = pts.reduce((a, b) => a.x > b.x ? a : b); MainChart._scrubAt(S.chart.scales.x.getPixelForValue(p.x)); })()""")
    tip = page.evaluate("""(() => { const t = document.getElementById('mc-tip'), b = document.getElementById('mc-box').getBoundingClientRect(),
        r = t.getBoundingClientRect(); return { text: t.innerText, hidden: t.hidden, inside: r.left >= b.left - 0.5 && r.right <= b.right + 0.5,
        fits: t.scrollWidth <= t.clientWidth + 1 }; })()""")
    flat = ' '.join(tip['text'].split())
    check(f'{label}: chart tooltip shows the full long note', not tip['hidden'] and ' '.join((NOTE + TOKEN).split()) in flat, flat[:60])
    check(f'{label}: chart tooltip text wraps inside it, tooltip inside the chart', tip['fits'] and tip['inside'], str(tip | {'text': ''}))
    if args.shots:
        page.locator('#main-chart').screenshot(path=f'{args.shots}/after-{label}-chart-tooltip-long-note.png')
    check(f'{label}: no page errors', not errors, '; '.join(errors[:3]))
    ctx.close()


with sync_playwright() as pw:
    b = getattr(pw, args.engine).launch()
    run(b, 'wide', {'width': 1920, 'height': 1080}, False)
    run(b, 'desktop', {'width': 1280, 'height': 900}, False)
    run(b, 'iphone', {'width': 390, 'height': 844}, True)
    b.close()
print('FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED')
sys.exit(1 if failures else 0)
