"""
At-a-glance tank state for the Parameters page: tiles, staleness, CO2 pH drop.
The pure functions take plain objects (anything with .timestamp/.value/...) so tests need no DB.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.catalog import PARAMETERS, STALE_DAYS, CO2_DROP, CO2_DROP_LABEL, TILE_GROUPS

SPARK_DAYS = 30
CO2_TANK_DAYS = 2        # in-tank pH (inside the CO2 window) must be this recent
CO2_DEGASSED_DAYS = 14   # degassed pH reference must be this recent


def age_days(ts, now):
    return (now - ts).total_seconds() / 86400


def is_stale(key, ts, now):
    limit = STALE_DAYS.get(key)
    return limit is not None and age_days(ts, now) > limit


def age_text(ts, time_known, now):
    """'just now', '40 min ago', '5 h ago', '2 d ago'. Date-only readings count whole days."""
    if not time_known:
        days = (now.date() - ts.date()).days
        return 'today' if days <= 0 else ('yesterday' if days == 1 else f'{days} d ago')
    mins = (now - ts).total_seconds() / 60
    if mins < 5:
        return 'just now'
    if mins < 60:
        return f'{int(mins)} min ago'
    if mins < 48 * 60:
        return f'{int(mins // 60)} h ago'
    return f'{int(mins // 1440)} d ago'


def band_state(value, target):
    """'in' / 'out' / None (no target). target: (min, max), either may be None."""
    if not target:
        return None
    lo, hi = target
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        return 'out'
    return 'in'


def in_window(ts, on, off):
    """Is ts's time of day inside the daily window [on, off)? Handles windows that cross midnight."""
    t = ts.time()
    return on <= t < off if on <= off else (t >= on or t < off)


@dataclass
class Pair:
    degassed: object      # the ph_degassed reading (KH-driven reference)
    tank: object          # the in-tank ph reading, taken inside the CO2 window

    @property
    def timestamp(self):  # when this pair became available
        return max(self.degassed.timestamp, self.tank.timestamp)

    @property
    def value(self):
        return round(self.degassed.value - self.tank.value, 2)

    time_known = True
    quality = 'ok'        # only ok readings are ever paired


def co2_drop_at(readings, on, off, at):
    """CO2 pH drop as of `at`: (degassed, tank), either None if missing.
    degassed: most recent ok (not suspect, not bad) degassed pH within CO2_DEGASSED_DAYS.
    tank: most recent ok in-tank pH with a known time inside the CO2 window, within CO2_TANK_DAYS."""
    ok = [r for r in readings if r.quality == 'ok' and r.timestamp <= at]
    deg = [r for r in ok if r.parameter == 'ph_degassed' and r.timestamp >= at - timedelta(days=CO2_DEGASSED_DAYS)]
    tank = [r for r in ok if r.parameter == 'ph' and r.time_known and in_window(r.timestamp, on, off)
            and r.timestamp >= at - timedelta(days=CO2_TANK_DAYS)]
    latest = lambda rs: max(rs, key=lambda r: (r.timestamp, r.id or 0)) if rs else None
    return latest(deg), latest(tank)


def co2_series(readings, on, off):
    """The drop over time: the rule evaluated at each reading that could change it. Oldest first."""
    pairs, seen = [], set()
    times = sorted({r.timestamp for r in readings if r.quality == 'ok' and r.parameter in ('ph', 'ph_degassed')})
    for t in times:
        deg, tank = co2_drop_at(readings, on, off, t)
        if deg and tank and (id(deg), id(tank)) not in seen:
            seen.add((id(deg), id(tank)))
            pairs.append(Pair(deg, tank))
    return pairs


def spark(points, now, target=None, days=SPARK_DAYS, w=120, h=32):
    """SVG geometry for a sparkline over the last `days`: {'line', 'dots', 'band'} in a w x h box,
    or None if no point falls in the window. points: objects with timestamp/value/quality."""
    start = now - timedelta(days=days)
    pts = [p for p in points if start <= p.timestamp <= now]
    if not pts:
        return None
    # scale on ok readings so one suspect outlier doesn't flatten the rest; suspects clamp to the edge
    vals = [p.value for p in pts if p.quality != 'suspect'] or [p.value for p in pts]
    lo, hi = target if target else (None, None)
    ys = vals + [v for v in (lo, hi) if v is not None]
    vmin, vmax = min(ys), max(ys)
    if vmax == vmin:
        vmin, vmax = vmin - 1, vmax + 1
    pad = 3
    x = lambda t: round(pad + (w - 2 * pad) * (t - start).total_seconds() / (days * 86400), 1)
    y = lambda v: round(h - pad - (h - 2 * pad) * (min(max(v, vmin), vmax) - vmin) / (vmax - vmin), 1)
    band = None
    if target and (lo is not None or hi is not None):
        top, bottom = y(hi if hi is not None else vmax), y(lo if lo is not None else vmin)
        band = {'y': min(top, bottom), 'h': max(abs(bottom - top), 1)}
    return {'w': w, 'h': h, 'band': band,
            'line': ' '.join(f'{x(p.timestamp)},{y(p.value)}' for p in pts),
            'dots': [{'x': x(p.timestamp), 'y': y(p.value), 'suspect': p.quality == 'suspect'} for p in pts]}


def _tile(key, label, unit, last, target, now, pts):
    return {
        'key': key, 'label': label, 'unit': '' if unit == 'pH' else unit,
        'value': last.value, 'timestamp': last.timestamp, 'time_known': last.time_known,
        'age': age_text(last.timestamp, last.time_known, now),
        'stale': is_stale(key, last.timestamp, now),
        'suspect': last.quality == 'suspect',
        'band': band_state(last.value, target), 'target': target,
        'method': getattr(last, 'method', None),
        'value_min': getattr(last, 'value_min', None), 'value_max': getattr(last, 'value_max', None),
        'spark': spark(pts, now, target),
    }


def co2_tile(readings, target, now, window):
    """None without a window. Otherwise a tile; if a reading is missing it has no value, only a message."""
    if not window or None in window:
        return None
    on, off = window
    deg, tank = co2_drop_at(readings, on, off, now)
    if deg and tank:
        pair = Pair(deg, tank)
        tile = _tile(CO2_DROP, CO2_DROP_LABEL, 'pH', pair, target, now, co2_series(readings, on, off))
        tile['pairing'] = pair
        return tile
    return {'key': CO2_DROP, 'label': CO2_DROP_LABEL, 'value': None, 'stale': True, 'target': target,
            'message': 'no in-window pH' if not tank else f'no degassed pH in {CO2_DEGASSED_DAYS} d',
            'window': window, 'spark': spark(co2_series(readings, on, off), now, target)}


def bubble_tile(event, now):
    return {'key': 'co2_bubble_rate', 'label': 'CO2 bubble rate', 'unit': '/30s', 'value': event.value,
            'timestamp': event.timestamp, 'time_known': event.time_known, 'bubble': True,
            'age': age_text(event.timestamp, event.time_known, now), 'stale': False, 'suspect': False,
            'band': None, 'target': None, 'method': event.notes, 'value_min': None, 'value_max': None, 'spark': None}


def build_tiles(readings, targets, now, co2_window=None, bubble=None):
    """readings: all of one tank's readings. targets: {key: (min, max)}. co2_window: (on, off) times or None.
    bubble: latest bubble-rate event or None. Returns TILE_GROUPS order as a list of non-empty groups.
    Bad readings never count as latest; a suspect latest is shown but flagged."""
    by_param = {}
    for r in sorted(readings, key=lambda r: (r.timestamp, r.id or 0)):
        if r.quality != 'bad' and r.parameter in PARAMETERS:
            by_param.setdefault(r.parameter, []).append(r)
    tiles = {k: _tile(k, *PARAMETERS[k][:2], pts[-1], targets.get(k), now, pts) for k, pts in by_param.items()}
    co2 = co2_tile(readings, targets.get(CO2_DROP), now, co2_window)
    if co2:
        tiles[CO2_DROP] = co2
    if bubble is not None and bubble.value is not None:
        tiles['co2_bubble_rate'] = bubble_tile(bubble, now)

    placed = [k for g in TILE_GROUPS for k in g]
    groups = [[tiles[k] for k in g if k in tiles] for g in TILE_GROUPS]
    groups.append([tiles[k] for k in sorted(tiles) if k not in placed])
    return [g for g in groups if g]


def fmt_target(target):
    lo, hi = target
    g = lambda v: '%g' % v
    if lo is not None and hi is not None:
        return f'{g(lo)}–{g(hi)}'
    return f'≥ {g(lo)}' if lo is not None else f'≤ {g(hi)}'


def _iso(ts):
    return ts.isoformat(timespec='minutes')


def series(key, readings, events, targets, co2_window=None):
    """Everything the main chart needs for one tile key, all time (the client windows it).
    Readings include bad ones (hidden by default in the UI); events are all of the tank's."""
    from app.catalog import EVENT_TYPES
    out = {'key': key, 'target': targets.get(key), 'step': False,
           'events': [{'t': _iso(e.timestamp), 'time_known': e.time_known, 'type': e.event_type,
                       'label': EVENT_TYPES.get(e.event_type, (e.event_type, None))[0],
                       'unit': EVENT_TYPES.get(e.event_type, (None, None))[1], 'value': e.value, 'notes': e.notes}
                      for e in sorted(events, key=lambda e: e.timestamp)]}
    if key == CO2_DROP:
        pairs = co2_series(readings, *co2_window) if co2_window and None not in co2_window else []
        out.update(label=CO2_DROP_LABEL, unit='pH', points=[
            {'t': _iso(p.timestamp), 'time_known': True, 'y': p.value, 'min': None, 'max': None,
             'quality': 'ok', 'method': None, 'notes': None,
             'pair': {'degassed': {'t': _iso(p.degassed.timestamp), 'time_known': p.degassed.time_known, 'y': p.degassed.value},
                      'tank': {'t': _iso(p.tank.timestamp), 'time_known': p.tank.time_known, 'y': p.tank.value}}}
            for p in pairs])
    elif key == 'co2_bubble_rate':
        out.update(label='CO2 bubble rate', unit='bubbles/30s', step=True, points=[
            {'t': e['t'], 'time_known': e['time_known'], 'y': e['value'], 'min': None, 'max': None,
             'quality': 'ok', 'method': None, 'notes': e['notes']}
            for e in out['events'] if e['type'] == 'co2_bubble_rate' and e['value'] is not None])
    elif key in PARAMETERS:
        out.update(label=PARAMETERS[key][0], unit=PARAMETERS[key][1], points=[
            {'t': _iso(r.timestamp), 'time_known': r.time_known, 'y': r.value, 'min': r.value_min, 'max': r.value_max,
             'quality': r.quality, 'method': r.method, 'notes': r.notes, 'id': r.id}
            for r in sorted(readings, key=lambda r: (r.timestamp, r.id or 0)) if r.parameter == key])
    else:
        return None
    return out
