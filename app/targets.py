"""Per-tank target ranges: validation and save. Shared by the Manage page form and JSON."""
import math

from app.catalog import TARGET_KEYS, TARGET_RANGES
from app.models import db, TargetRange
from app.utils import parse_number


def clean_target(key, raw_min, raw_max):
    """-> (min, max), either None. Raises ValueError with a readable message."""
    if key not in TARGET_KEYS:
        raise ValueError(f'unknown parameter {key!r}')
    label = TARGET_KEYS[key]
    vals = []
    for end, raw in (('min', raw_min), ('max', raw_max)):
        try:
            v = parse_number(raw)
        except ValueError:
            raise ValueError(f'{label} {end}: {raw!r} is not a number')
        if v is not None:
            lo, hi = TARGET_RANGES[key]
            if not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError(f'{label} {end}: {raw} is outside the plausible range {lo}–{hi}')
        vals.append(v)
    if None not in vals and vals[0] > vals[1]:
        raise ValueError(f'{label}: min is above max')
    return tuple(vals)


def save_targets(aquarium, data):
    """data: {key: (min, max)} raw values for any subset of keys. All-or-nothing: every entry is
    validated before anything is written. Both ends blank removes that target."""
    cleaned = {k: clean_target(k, lo, hi) for k, (lo, hi) in data.items()}
    existing = {t.parameter: t for t in aquarium.targets}
    for key, (lo, hi) in cleaned.items():
        row = existing.get(key)
        if lo is None and hi is None:
            if row:
                db.session.delete(row)
        elif row:
            row.min, row.max = lo, hi
        else:
            db.session.add(TargetRange(aquarium_id=aquarium.id, parameter=key, min=lo, max=hi))
    db.session.commit()


def targets_for(aquarium_id):
    return {t.parameter: (t.min, t.max) for t in TargetRange.query.filter_by(aquarium_id=aquarium_id)}
