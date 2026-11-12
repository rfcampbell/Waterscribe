"""Browser check for the Parameters log: collapsible days, summaries, filter, session memory, WCAG AA contrast,
and that the entry form is only in the drawer (Playwright, dev venv only):
    .venv-dev/bin/python tests/ui_log_check.py http://127.0.0.1:5055 --tank 4 [--shots DIR]
Read-only: every non-GET request is blocked and fails the run, so it is safe against prod."""
import argparse
import sys

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument('base')
ap.add_argument('--tank', type=int, required=True)
ap.add_argument('--shots')
args = ap.parse_args()
failures = []


def check(name, cond, detail=''):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")
    if not cond:
        failures.append(name)


# Effective contrast of every visible text node under the given roots: text colour (alpha x ancestor
# opacity) over the composited ancestor backgrounds. Where the stack isn't opaque, the page gradient
# shows through, so the worst of its three stops is used.
CONTRAST_JS = r"""(roots) => {
  const parse = c => { const m = c.match(/[\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m.length > 3 ? m[3] : 1 }; };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = c => { const t = [c.r, c.g, c.b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
                     return 0.2126 * t[0] + 0.7152 * t[1] + 0.0722 * t[2]; };
  const ratio = (x, y) => { const [a, b] = [lum(x), lum(y)].sort((p, q) => q - p); return (a + 0.05) / (b + 0.05); };
  const STOPS = ['rgb(10,22,40)', 'rgb(26,47,79)', 'rgb(45,74,111)'].map(parse);
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const inRoots = n => roots.some(sel => [...document.querySelectorAll(sel)].some(r => r.contains(n)));
  for (let n; (n = walker.nextNode());) {
    if (!n.textContent.trim() || !inRoots(n)) continue;
    const el = n.parentElement, rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height || el.closest('[hidden]') || el.closest('[aria-hidden="true"]')) continue;
    let opacity = 1, chain = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      opacity *= +cs.opacity;
      if (cs.display === 'none' || cs.visibility === 'hidden') { opacity = 0; break; }
      chain.push(parse(cs.backgroundColor));
    }
    if (opacity < 0.05) continue;   // invisible until hover/focus (e.g. the ⋯ button on desktop)
    const cs = getComputedStyle(el), fg = parse(cs.color); fg.a *= opacity;
    let worst = 99;
    for (const stop of STOPS) {
      let bg = stop;
      for (const c of chain.slice().reverse()) if (c.a) bg = over(c, bg);
      worst = Math.min(worst, ratio(over(fg, bg), bg));
    }
    const size = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    out.push({ text: n.textContent.trim().slice(0, 30), cls: el.className, ratio: Math.round(worst * 100) / 100, need });
  }
  return out;
}"""


def run(p, label, viewport, mobile):
    print(f'== {label}')
    b = p.chromium.launch()
    ctx = b.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    page = ctx.new_page()
    errors, writes = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('**/*', lambda r: r.continue_() if r.request.method in ('GET', 'HEAD')
               else (writes.append(f'{r.request.method} {r.request.url}'), r.abort()))

    def shot(name):
        if args.shots:
            page.evaluate("document.querySelector('.log-section').scrollIntoView({block: 'start'})")
            page.wait_for_timeout(250)   # let chevron rotations finish
            page.screenshot(path=f'{args.shots}/after-{label}-{name}.png')

    url = f'{args.base}/?aquarium_id={args.tank}'
    resp = page.goto(url)
    page.wait_for_selector('#readings-log .log-day')
    check('page is served no-cache', 'no-cache' in (resp.headers.get('cache-control') or ''), resp.headers.get('cache-control'))

    # 1. entry form only in the drawer; page order pills -> tiles -> chart -> log
    check('entry form not visible on the page', not page.is_visible('#readings-form'))
    check('form lives only inside the drawer', page.evaluate("document.querySelectorAll('form#readings-form').length === 1 && !!document.querySelector('#entry-drawer #readings-form')"))
    check('no "Water Parameters" inline section', page.get_by_text('Water Parameters', exact=True).count() == 0)
    order = page.evaluate("""['.tank-pills', '#tiles', '#main-chart', '#readings-log'].map(s => document.querySelector(s).getBoundingClientRect().top + scrollY)""")
    check('order: pills, tiles, chart, log', order == sorted(order), str([round(x) for x in order]))
    check('button reads "+ Add new entry"', page.text_content('#log-btn').strip().startswith('+ Add new entry'))
    page.click('#log-btn')
    check('drawer keeps per-parameter collapse', page.locator('#entry-drawer .pgroup .pg-toggle').count() > 5)
    page.keyboard.press('Escape')

    # 2. collapsed by default, with summaries
    days = page.locator('#readings-log .log-day')
    n = days.count()
    check('all days collapsed by default', page.locator('#readings-log .log-day.open').count() == 0 and
          page.evaluate("[...document.querySelectorAll('#readings-log .ltable')].every(t => t.hidden)"), f'{n} days')
    sums = page.evaluate("""[...document.querySelectorAll('#readings-log .log-day')].map(s => ({
        date: s.dataset.date, text: s.querySelector('.day-toggle').innerText.replace(/\\s+/g, ' ').trim(),
        rows: s.querySelectorAll('.lread').length, events: s.querySelectorAll('.levent').length,
        warn: s.querySelectorAll('.lread.q-suspect, .lread.q-bad').length }))""")
    def matches(d):
        t = d['text']
        return ((not d['rows'] or f"{d['rows']} reading" in t) and (not d['events'] or f"{d['events']} event" in t)
                and ((f"⚠ {d['warn']}" in t) if d['warn'] else '⚠' not in t))
    wrong = [d for d in sums if not matches(d)]
    check('every summary matches its rows (counts, ⚠)', sums and not wrong,
          f'{len(sums)} days' if not wrong else '; '.join(f"{d['date']}: {d['text']}" for d in wrong[:3]))
    first = sums[0]['text'] if sums else ''
    print(f'      e.g. {first}')
    has_keys = page.evaluate("[...document.querySelectorAll('.day-sum .k')].length > 0")
    check('summaries show key values inline', has_keys)
    # summary labels stand for the tiles: hover title is the tile's label; degassed pH is "pH dg", never "dpH"
    lab = page.evaluate("""(() => {
        const tiles = Object.fromEntries([...document.querySelectorAll('#tiles .tile')].map(t => [t.dataset.key, t.querySelector('.tile-label').textContent.trim()]));
        const ks = [...document.querySelectorAll('.day-sum .k')].map(k => [k.textContent, k.title]);
        return { tiles, used: [...new Map(ks).entries()] };
    })()""")
    tile_labels = set(lab['tiles'].values())
    stray = [u for u in lab['used'] if u[1] not in tile_labels]
    check('every summary label is titled with a tile label', lab['used'] and not stray, str(lab['used']) if not stray else str(stray))
    split = page.evaluate("""[...document.querySelectorAll('.day-sum .kp')].filter(e => e.getClientRects().length > 1).map(e => e.textContent)""")
    check('label and value never split across lines', not split, str(split[:3]))
    shorts = dict(lab['used'])
    check('no "dpH" label; degassed pH reads "pH dg"', 'dpH' not in shorts and
          ('pH dg' not in shorts or shorts['pH dg'] == lab['tiles'].get('ph_degassed')),
          f"pH dg -> {shorts.get('pH dg')!r}" if 'pH dg' in shorts else 'no degassed pH on these days')
    shot('log-collapsed')

    # toggle one, reload: remembered for the session; a new session starts collapsed
    page.click('#readings-log .log-day >> nth=0 >> .day-toggle')
    d0 = sums[0]['date']
    check('header toggles a day open', page.evaluate(f"!document.getElementById('day-{d0}').hidden") and
          page.get_attribute('#readings-log .log-day >> nth=0 >> .day-toggle', 'aria-expanded') == 'true')
    shot('log-day-open')
    page.reload(); page.wait_for_selector('#readings-log .log-day')
    check('open day remembered across reload', page.evaluate(f"!document.getElementById('day-{d0}').hidden"))
    page2 = ctx.browser.new_context(viewport=viewport).new_page()
    page2.route('**/*', lambda r: r.continue_() if r.request.method in ('GET', 'HEAD') else r.abort())
    page2.goto(url); page2.wait_for_selector('#readings-log .log-day')
    check('new session starts collapsed', page2.locator('#readings-log .log-day.open').count() == 0)
    page2.context.close()

    # expand / collapse all
    page.click('.log-tools >> text=Expand all')
    check('Expand all opens every day', page.locator('#readings-log .log-day.open').count() == n)
    shot('log-expanded')

    # 3. contrast: every visible text in the log, expanded, plus the header controls
    res = page.evaluate(CONTRAST_JS, ['#readings-log', '.log-tools', '#log-chips', '.log-section .lhead'])
    bad = [r for r in res if r['ratio'] < r['need']]
    low = min(res, key=lambda r: r['ratio']) if res else None
    check('WCAG AA contrast on all log text', res and not bad,
          f"{len(res)} text nodes, lowest {low['ratio']} ({low['cls']}: {low['text']!r})" if not bad else
          '; '.join(f"{r['ratio']}<{r['need']} {r['cls']}: {r['text']!r}" for r in bad[:4]))
    seps = page.evaluate("""(() => { const bg = s => getComputedStyle(document.querySelector(s)).backgroundColor;
        return { card: bg('.log-section'), row: bg('.lread'), event: document.querySelector('.levent') ? bg('.levent') : null }; })()""")
    check('rows, events and card have distinct opaque backgrounds',
          len({seps['card'], seps['row'], seps['event']} - {None}) == (3 if seps['event'] else 2)
          and not any('rgba' in (v or '') for v in seps.values()), str(seps))
    if seps['event']:
        bar = page.evaluate("getComputedStyle(document.querySelector('.levent')).borderLeftWidth")
        check('event rows keep their accent bar', bar == '3px', bar)

    page.click('.log-tools >> text=Collapse all')
    check('Collapse all closes every day', page.locator('#readings-log .log-day.open').count() == 0)

    # filter chips: summaries follow the filter
    chip = page.locator('#log-chips .chip:not(.active)').nth(0)
    pname = chip.inner_text()
    chip.click()
    fsums = page.evaluate("""[...document.querySelectorAll('#readings-log .log-day')].map(s => ({
        text: s.querySelector('.day-sum').innerText, rows: s.querySelectorAll('.lread').length,
        params: [...new Set([...s.querySelectorAll('.lread .c-param')].map(e => e.textContent))] }))""")
    check(f'filter "{pname}": only matching rows, summaries count them',
          fsums and all(f['params'] == [pname] and f"{f['rows']} reading" in f['text'] for f in fsums),
          f"{len(fsums)} days, e.g. {fsums[0]['text'] if fsums else ''}")
    check('filter: collapsed state kept', page.locator('#readings-log .log-day.open').count() == 0)
    shot('log-filtered')

    check('no writes attempted', not writes, '; '.join(writes))
    check('no page errors', not errors, '; '.join(errors[:3]))
    b.close()


with sync_playwright() as p:
    run(p, 'desktop', {'width': 1280, 'height': 900}, False)
    run(p, 'iphone', {'width': 390, 'height': 844}, True)
print('FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED')
sys.exit(1 if failures else 0)
