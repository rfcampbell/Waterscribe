"""Browser check for the tile grid and the main chart's y scale (Playwright, dev venv only):
    .venv-dev/bin/python tests/ui_tiles_chart_check.py http://127.0.0.1:5055 --tank 4 [--shots DIR]
Read-only: non-GET requests are blocked. The chart part answers one /series request with the real data
plus injected outliers (suspect high, suspect low, bad high) and a target band, so it doesn't depend
on what the tank happens to hold."""
import argparse
import os
import runpy
import sys

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('base')
ap.add_argument('--tank', type=int, required=True)
ap.add_argument('--key', default='ph')
ap.add_argument('--shots')
args = ap.parse_args()
CAT = runpy.run_path(os.path.join(os.path.dirname(__file__), '..', 'app', 'catalog.py'))
ORDER = [k for g in CAT['TILE_GROUPS'] for k in g]
failures = []


def check(name, cond, detail=''):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")
    if not cond:
        failures.append(name)


# accent contrast: the 3px strip vs the tile body beside it, both over the page gradient's stops
ACCENT_JS = r"""() => {
  const parse = c => { const m = c.match(/[\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m.length > 3 ? m[3] : 1 }; };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = c => { const t = [c.r, c.g, c.b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
                     return 0.2126 * t[0] + 0.7152 * t[1] + 0.0722 * t[2]; };
  const ratio = (x, y) => { const [a, b] = [lum(x), lum(y)].sort((p, q) => q - p); return (a + 0.05) / (b + 0.05); };
  const STOPS = ['rgb(10,22,40)', 'rgb(26,47,79)', 'rgb(45,74,111)'].map(parse);
  const out = {};
  for (const t of document.querySelectorAll('#tiles .tile:not(.stale)')) {
    const grp = [...t.classList].find(c => c.startsWith('grp-'));
    if (!grp || out[grp]) continue;
    const cs = getComputedStyle(t), accent = cs.getPropertyValue('--grp').trim();
    const probe = document.createElement('i'); probe.style.color = accent; document.body.append(probe);
    const a = parse(getComputedStyle(probe).color); probe.remove();
    const body = parse(cs.backgroundColor);
    out[grp] = { accent: getComputedStyle(probe).color || accent, img: cs.backgroundImage.slice(0, 60), size: cs.backgroundSize,
                 ratio: Math.min(...STOPS.map(s => ratio(a, over(body, s)))) };
  }
  return out;
}"""


def tiles(p, label, viewport, mobile, cols_want=None):
    ctx = p.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    page = ctx.new_page()
    page.route('**/*', lambda r: r.continue_() if r.request.method in ('GET', 'HEAD') else r.abort())
    page.goto(f'{args.base}/?aquarium_id={args.tank}')
    page.wait_for_selector('#tiles .tile')
    info = page.evaluate("""() => {
        const grid = document.getElementById('tiles'), ts = [...grid.querySelectorAll('.tile')];
        const cols = getComputedStyle(grid).gridTemplateColumns.split(' ').length;
        const rows = {}; ts.forEach(t => { const y = Math.round(t.getBoundingClientRect().top); rows[y] = (rows[y] || 0) + 1; });
        return { n: ts.length, parents: new Set(ts.map(t => t.parentElement)).size, cols, rows: Object.values(rows),
                 keys: ts.map(t => t.dataset.key), grps: ts.map(t => ([...t.classList].find(c => c.startsWith('grp-')) || '')),
                 minW: Math.min(...ts.map(t => t.getBoundingClientRect().width)), gridW: grid.getBoundingClientRect().width };
    }""")
    print(f"== tiles {label}: {info['n']} tiles, {info['cols']} columns, rows {info['rows']}, grid {round(info['gridW'])}px")
    check(f'{label}: one grid, no per-group rows', info['parents'] == 1 and page.locator('.tile-groups').count() == 0)
    check(f'{label}: TILE_GROUPS order kept', info['keys'] == sorted(info['keys'], key=lambda k: ORDER.index(k) if k in ORDER else 99),
          ' '.join(info['keys']))
    check(f'{label}: every row full except the last', all(r == info['cols'] for r in info['rows'][:-1]), str(info['rows']))
    if cols_want:
        check(f'{label}: {cols_want} columns', info['cols'] == cols_want, str(info['cols']))
    else:
        check(f'{label}: columns fill the width at >= 210px', info['minW'] >= 210 and info['cols'] == int((info['gridW'] + 10) // 220),
              f"{info['cols']} cols, narrowest {round(info['minW'])}px")
    want_grp = [f"grp-{CAT['TILE_GROUP_OF'][k]}" if k in CAT['TILE_GROUP_OF'] else '' for k in info['keys']]
    check(f'{label}: each tile has its group accent class', info['grps'] == want_grp)
    acc = page.evaluate(ACCENT_JS)
    check(f'{label}: accents drawn as a 3px top strip', acc and all(a['size'].endswith('3px') and 'gradient' in a['img'] for a in acc.values()),
          str({k: a['size'] for k, a in acc.items()}))
    check(f'{label}: accents >= 3:1 against the tile (non-text AA)', acc and all(a['ratio'] >= 3 for a in acc.values()),
          ', '.join(f"{k} {a['ratio']:.2f}" for k, a in acc.items()))
    check(f'{label}: three distinct accents', len({a['accent'] for a in acc.values()}) == len(acc) == 3)
    if args.shots:
        page.locator('#tiles').scroll_into_view_if_needed()
        page.screenshot(path=f"{args.shots}/after-{label}-tiles.png", full_page=False)
    ctx.close()


CHART_STATE_JS = """() => {
    const S = MainChart._state, c = S.chart, a = c.chartArea, y = c.scales.y;
    const sets = c.data.datasets.map(ds => ds.data.filter(d => !d.synthetic && d.x >= S.win[0] && d.x <= S.win[1])
        .map(d => ({ x: d.x, real: d.real, y: d.y, clip: d.clip, q: d.quality })));
    return { min: y.min, max: y.max, top: a.top, bottom: a.bottom, sets, target: S.data.target };
}"""


def chart(p, label, viewport, mobile):
    print(f'== chart {label}')
    ctx = p.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    inj = {}

    def series(route):
        r = route.fetch()
        data = r.json()
        ok = [pt['y'] for pt in data['points'] if pt.get('quality') == 'ok']
        lo, hi = (min(ok), max(ok)) if ok else (0, 1)
        span = (hi - lo) or 1
        from datetime import datetime, timedelta
        t = lambda d: (datetime.now() - timedelta(days=d)).strftime('%Y-%m-%dT%H:%M')
        extra = [dict(t=t(3), y=round(hi + 20 * span, 2), quality='suspect', tag='suspect-high'),
                 dict(t=t(5), y=round(lo - 15 * span, 2), quality='suspect', tag='suspect-low'),
                 dict(t=t(4), y=round(hi + 40 * span, 2), quality='bad', tag='bad-high')]
        for e in extra:
            data['points'].append({**e, 'time_known': True, 'min': None, 'max': None, 'method': None, 'notes': None})
        data['points'].sort(key=lambda pt: pt['t'])
        data['target'] = [round(lo - 0.5 * span, 2), round(hi + 0.5 * span, 2)]   # outside the ok spread: must widen the scale
        inj.update(lo=lo, hi=hi, extra=extra, target=data['target'])
        route.fulfill(json=data)
    page.route('**/*', lambda r: r.continue_() if r.request.method in ('GET', 'HEAD') else r.abort())
    page.route(f'**/api/aquarium/{args.tank}/series?key={args.key}', series)
    page.goto(f'{args.base}/?aquarium_id={args.tank}')
    page.wait_for_selector('#tiles .tile')
    page.click(f'#tiles .tile[data-key="{args.key}"]')
    page.wait_for_function('MainChart._state.data && MainChart._state.chart && MainChart._state.key === %r' % args.key)
    page.click('.mc-ranges button[data-days="30"]')
    page.wait_for_timeout(200)

    def verify(show_bad):
        st = page.evaluate(CHART_STATE_JS)
        allp = [d for s in st['sets'] for d in s]
        ok = [d['real'] for d in allp if d['q'] == 'ok']
        tg = st['target']
        tag = 'bad on' if show_bad else 'bad off'
        check(f'{tag}: scale covers ok readings and target', st['min'] <= min(ok + tg) and st['max'] >= max(ok + tg),
              f"{st['min']:.2f}..{st['max']:.2f} vs ok {min(ok)}..{max(ok)}, target {tg}")
        pad = st['max'] - max(ok + tg)
        check(f'{tag}: scale has padding but ignores outliers', 0 < pad < (max(ok + tg) - min(ok + tg)) * 0.25,
              f'pad {pad:.3f}')
        by_tag = {e['tag']: e for e in inj['extra']}
        def find(e):
            return next((d for d in allp if abs(d['real'] - e['y']) < 1e-9 and d['q'] == e['quality']), None)
        sh, sl, bh = find(by_tag['suspect-high']), find(by_tag['suspect-low']), find(by_tag['bad-high'])
        check(f'{tag}: suspect high pinned to top edge', sh and sh['clip'] == 'up' and sh['y'] == st['max'], str(sh))
        check(f'{tag}: suspect low pinned to bottom edge', sl and sl['clip'] == 'down' and sl['y'] == st['min'], str(sl))
        check(f'{tag}: ok readings never pinned', all(not d['clip'] for d in allp if d['q'] == 'ok'))
        if show_bad:
            check('bad on: bad high pinned to top edge', bh and bh['clip'] == 'up', str(bh))
        else:
            check('bad off: bad point not drawn', bh is None)
        # marker pixels: the triangle just inside the edge is sand for suspect
        for e, edge in ((sh, 'top'), (sl, 'bottom')):
            px = page.evaluate(f"""(() => {{ const c = MainChart._state.chart, a = c.chartArea, x = c.scales.x.getPixelForValue({e['x']});
                const y = {'a.top + 6' if edge == 'top' else 'a.bottom - 6'}, k = c.currentDevicePixelRatio;
                return [...c.ctx.getImageData(Math.round(x * k), Math.round(y * k), 1, 1).data]; }})()""")
            check(f"{tag}: {edge} marker drawn in sand", abs(px[0] - 0xf7) < 30 and abs(px[1] - 0xb2) < 30 and abs(px[2] - 0x67) < 40, str(px))
        # tooltip keeps the real value
        for e in (sh, sl) + ((bh,) if show_bad else ()):
            page.evaluate(f"MainChart._scrubAt(MainChart._state.chart.scales.x.getPixelForValue({e['x']}))")
            tip = page.inner_text('#mc-tip')
            check(f"{tag}: tooltip shows real {e['q']} value {e['real']:g}", f"{e['real']:g}" in tip and e['q'] in tip.lower(),
                  tip.replace('\n', ' | ')[:80])
        return st

    st0 = verify(False)
    if args.shots:
        page.locator('#main-chart').scroll_into_view_if_needed()
        page.evaluate("MainChart._scrubAt(MainChart._state.chart.scales.x.getPixelForValue(%r))" % next(
            d['x'] for s in st0['sets'] for d in s if d['clip'] == 'up'))
        page.locator('#main-chart').screenshot(path=f'{args.shots}/after-{label}-chart-outliers.png')
    page.check('#mc-bad')
    page.wait_for_timeout(150)
    st1 = verify(True)
    check('bad on: scale unchanged by bad readings', (st1['min'], st1['max']) == (st0['min'], st0['max']))
    if args.shots:
        page.locator('#main-chart').screenshot(path=f'{args.shots}/after-{label}-chart-outliers-bad.png')
    check(f'{label}: no page errors', not errors, '; '.join(errors[:3]))
    ctx.close()


with sync_playwright() as pw:
    b = pw.chromium.launch()
    tiles(b, 'wide', {'width': 1920, 'height': 1080}, False)
    tiles(b, 'desktop', {'width': 1280, 'height': 900}, False)
    tiles(b, 'iphone', {'width': 390, 'height': 844}, True, cols_want=2)
    chart(b, 'desktop', {'width': 1280, 'height': 900}, False)
    chart(b, 'iphone', {'width': 390, 'height': 844}, True)
    b.close()
print('FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED')
sys.exit(1 if failures else 0)
