"""
At-a-glance tank state for the Parameters page: tiles, staleness, CO2 pH drop.
The pure functions take plain objects (anything with .timestamp/.value/...) so tests need no DB.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.catalog import PARAMETERS, STALE_DAYS, CO2_DROP, CO2_DROP_LABEL, TILE_ORDER

SPARK_DAYS = 30
CO2_DROP_DAYS = 90   # a tank gets the CO2 drop tile if it has a pairing this recent


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


@dataclass
class Pair:
    degassed: object      # the ph_degassed reading
    tank: object          # the in-tank ph reading it was paired with
    timestamp: datetime   # the degassed reading's time (the drop is plotted there)

    @property
    def value(self):
        return round(self.degassed.value - self.tank.value, 2)

    @property
    def time_known(self):
        return self.degassed.time_known and self.tank.time_known

    @property
    def quality(self):
        return 'suspect' if 'suspect' in (self.degassed.quality, self.tank.quality) else 'ok'


def co2_pairs(readings):
    """One Pair per degassed reading that has an in-tank pH the same day: the one nearest in time,
    ties going to the earlier. Bad readings are skipped. Returns pairs oldest first."""
    good = [r for r in readings if r.quality != 'bad']
    tank = [r for r in good if r.parameter == 'ph']
    out = []
    for d in sorted((r for r in good if r.parameter == 'ph_degassed'), key=lambda r: r.timestamp):
        same_day = [t for t in tank if t.timestamp.date() == d.timestamp.date()]
        if same_day:
            best = min(same_day, key=lambda t: (abs((t.timestamp - d.timestamp).total_seconds()), t.timestamp))
            out.append(Pair(d, best, d.timestamp))
    return out


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


def build_tiles(readings, targets, now):
    """readings: all of one tank's readings. targets: {key: (min, max)}. Returns tiles in TILE_ORDER.
    Bad readings never count as latest; a suspect latest is shown but flagged."""
    by_param = {}
    for r in sorted(readings, key=lambda r: (r.timestamp, r.id or 0)):
        if r.quality != 'bad' and r.parameter in PARAMETERS:
            by_param.setdefault(r.parameter, []).append(r)
    series = dict(by_param)
    pairs = co2_pairs(readings)
    if pairs and age_days(pairs[-1].timestamp, now) <= CO2_DROP_DAYS:
        series[CO2_DROP] = pairs

    tiles = []
    for key in TILE_ORDER + sorted(set(series) - set(TILE_ORDER)):
        pts = series.get(key)
        if not pts:
            continue
        last = pts[-1]
        target = targets.get(key)
        label, unit = (CO2_DROP_LABEL, 'pH') if key == CO2_DROP else PARAMETERS[key][:2]
        tile = {
            'key': key, 'label': label, 'unit': '' if unit == 'pH' else unit,
            'value': last.value, 'timestamp': last.timestamp, 'time_known': last.time_known,
            'age': age_text(last.timestamp, last.time_known, now),
            'stale': is_stale(key, last.timestamp, now),
            'suspect': last.quality == 'suspect',
            'band': band_state(last.value, target), 'target': target,
            'method': getattr(last, 'method', None),
            'spark': spark(pts, now, target),
        }
        if key == CO2_DROP:
            tile['pairing'] = last
            tile['value_min'] = tile['value_max'] = None
        else:
            tile['value_min'], tile['value_max'] = last.value_min, last.value_max
        tiles.append(tile)
    return tiles


def fmt_target(target):
    lo, hi = target
    g = lambda v: '%g' % v
    if lo is not None and hi is not None:
        return f'{g(lo)}–{g(hi)}'
    return f'≥ {g(lo)}' if lo is not None else f'≤ {g(hi)}'
