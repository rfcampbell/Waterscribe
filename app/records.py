"""
Validation and CSV conversion for readings and events, shared by the API
and import_csv.py. The CSV format is the one exports produce, so an export
can be re-imported.
"""
import csv
import io
from datetime import datetime, date, time

from app.catalog import PARAMETERS, EVENT_TYPES, QUALITIES, UNIT_CONVERSIONS, norm_unit
from app.utils import parse_number

READING_COLUMNS = ['date', 'time', 'tank', 'parameter', 'value', 'value_min', 'value_max',
                   'unit', 'method', 'quality', 'notes']
EVENT_COLUMNS = ['date', 'time', 'tank', 'event', 'value', 'unit', 'notes']

NOON = time(12, 0)


def _text(v, limit=None):
    v = (v or '').strip() if isinstance(v, str) else v
    if v in ('', None):
        return None
    v = str(v)
    if limit and len(v) > limit:
        raise ValueError(f'too long (max {limit} characters)')
    return v


def parse_when(date_str, time_str=None):
    """('2026-11-05', '15:23') -> (datetime, True); missing time -> (date at 12:00, False)."""
    try:
        d = date.fromisoformat((date_str or '').strip())
    except ValueError:
        raise ValueError(f'bad date {date_str!r} (want YYYY-MM-DD)')
    t = (time_str or '').strip()
    if not t:
        return datetime.combine(d, NOON), False
    try:
        return datetime.combine(d, time.fromisoformat(t)), True
    except ValueError:
        raise ValueError(f'bad time {time_str!r} (want HH:MM)')


def when_from_json(data):
    """API payloads send 'date' + optional 'time'; neither means now."""
    if not data.get('date'):
        return datetime.now().replace(second=0, microsecond=0), True
    return parse_when(data.get('date'), data.get('time'))


def _number(data, field, label):
    try:
        return parse_number(data.get(field))
    except ValueError:
        raise ValueError(f'{label}: {data.get(field)!r} is not a number')


def clean_reading(data):
    """Validate a reading dict -> column values. Raises ValueError with a readable message."""
    key = (data.get('parameter') or '').strip()
    if key not in PARAMETERS:
        raise ValueError(f'unknown parameter {key!r}')
    label = PARAMETERS[key][0]
    value = _number(data, 'value', label)
    if value is None:
        raise ValueError(f'{label}: value is required')
    vmin, vmax = _number(data, 'value_min', label + ' min'), _number(data, 'value_max', label + ' max')
    if vmin is not None and vmax is not None and vmin > vmax:
        raise ValueError(f'{PARAMETERS[key][0]}: min is above max')
    quality = (data.get('quality') or 'ok').strip().lower()
    if quality not in QUALITIES:
        raise ValueError(f'quality must be one of {", ".join(QUALITIES)}')
    return {'parameter': key, 'value': value, 'value_min': vmin, 'value_max': vmax,
            'method': _text(data.get('method'), 100), 'quality': quality,
            'notes': _text(data.get('notes'))}


def clean_event(data):
    key = (data.get('event_type') or '').strip()
    if key not in EVENT_TYPES:
        raise ValueError(f'unknown event type {key!r}')
    return {'event_type': key, 'value': _number(data, 'value', EVENT_TYPES[key][0]),
            'notes': _text(data.get('notes'))}


def _fmt(v):
    return '' if v is None else ('%g' % v if isinstance(v, float) else str(v))


def _date_time(r):
    return r.timestamp.date().isoformat(), (r.timestamp.strftime('%H:%M') if r.time_known else '')


def readings_csv(readings, tank):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(READING_COLUMNS)
    for r in readings:
        unit = PARAMETERS.get(r.parameter, ('', ''))[1]
        w.writerow([*_date_time(r), tank, r.parameter, _fmt(r.value), _fmt(r.value_min),
                    _fmt(r.value_max), unit, r.method or '', r.quality, r.notes or ''])
    return out.getvalue()


def events_csv(events, tank):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(EVENT_COLUMNS)
    for e in events:
        unit = EVENT_TYPES.get(e.event_type, ('', None))[1] or ''
        w.writerow([*_date_time(e), tank, e.event_type, _fmt(e.value),
                    unit if e.value is not None else '', e.notes or ''])
    return out.getvalue()


# CSV event names that differ from catalog keys
EVENT_ALIASES = {
    'fertilizer_dose_set': ('fertilizer_dose', None),
    'dosing_pump_installed': ('equipment', 'Dosing pump installed'),
    'shells_removed': ('other', 'Shells removed'),
}


def reading_from_csv_row(row):
    """CSV dict -> (timestamp, time_known, cleaned reading). The unit must match the catalog or
    have a conversion in UNIT_CONVERSIONS; converted readings keep the original in their note."""
    ts, known = parse_when(row.get('date'), row.get('time'))
    key = (row.get('parameter') or '').strip().lower()
    cleaned = clean_reading({**row, 'parameter': key})
    expected, unit = PARAMETERS[key][1], (row.get('unit') or '').strip()
    if unit and norm_unit(unit) != norm_unit(expected):
        divisor = UNIT_CONVERSIONS.get((key, norm_unit(unit)))
        if not divisor:
            raise ValueError(f'unit {unit!r} for {key} (expected {expected!r})')
        orig = _fmt(cleaned['value']) + (f" ({_fmt(cleaned['value_min'])}–{_fmt(cleaned['value_max'])})"
                                          if cleaned['value_min'] is not None or cleaned['value_max'] is not None else '')
        for f in ('value', 'value_min', 'value_max'):
            if cleaned[f] is not None:
                cleaned[f] = round(cleaned[f] / divisor, 2)
        note = f'converted from {orig} {unit}'
        cleaned['notes'] = f"{cleaned['notes']}; {note}" if cleaned['notes'] else note
    return ts, known, cleaned


def event_from_csv_row(row):
    ts, known = parse_when(row.get('date'), row.get('time'))
    name = (row.get('event') or '').strip().lower()
    key, prefix = EVENT_ALIASES.get(name, (name, None))
    notes = '; '.join(x for x in (prefix, (row.get('notes') or '').strip()) if x) or None
    cleaned = clean_event({'event_type': key, 'value': row.get('value'), 'notes': notes})
    expected = EVENT_TYPES[key][1]
    unit = (row.get('unit') or '').strip()
    if unit and expected and norm_unit(unit) not in (norm_unit(expected), 'percent' if expected == '%' else None):
        raise ValueError(f'unit {unit!r} for {key} (expected {expected!r})')
    if cleaned['value'] is not None and not expected:
        raise ValueError(f'{key} does not take a value')
    return ts, known, cleaned
