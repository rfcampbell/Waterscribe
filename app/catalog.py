"""
Parameter and event catalogs. Keys are what the DB and CSVs store;
add a parameter or event type by adding a line here.
"""

# key: (label, unit, input step, chart group)
# Parameters sharing a chart group are drawn on the same chart.
PARAMETERS = {
    'ph':          ('pH', 'pH', '0.01', 'ph'),
    'ammonia':     ('Ammonia', 'ppm', '0.01', 'nitrogen'),
    'nitrite':     ('Nitrite', 'ppm', '0.01', 'nitrogen'),
    'nitrate':     ('Nitrate', 'ppm NO3', '0.5', 'nitrate'),
    'kh':          ('KH', 'dKH', '0.1', 'hardness'),
    'gh':          ('GH', 'dGH', '0.1', 'hardness'),
    'ec':          ('EC', 'µS/cm', '1', 'ec'),
    'ph_degassed': ('pH (degassed)', 'pH', '0.01', 'ph'),
    'temperature': ('Temperature', '°F', '0.1', 'temperature'),
    'tds':         ('TDS', 'ppm', '1', 'tds'),
    'phosphate':   ('Phosphate', 'ppm PO4', '0.05', 'phosphate'),
    'potassium':   ('Potassium', 'ppm K', '1', 'potassium'),
    'iron':        ('Iron', 'ppm Fe', '0.01', 'iron'),
}

CHART_GROUPS = {
    'ph': 'pH', 'nitrogen': 'Ammonia / Nitrite (ppm)', 'nitrate': 'Nitrate (ppm NO3)', 'hardness': 'KH / GH',
    'ec': 'EC (µS/cm)', 'temperature': 'Temperature (°F)', 'tds': 'TDS (ppm)', 'phosphate': 'Phosphate (ppm PO4)',
    'potassium': 'Potassium (ppm K)', 'iron': 'Iron (ppm Fe)',
}

# key: (label, unit or None if the event has no value)
# CO2 is tracked only as the bubble-rate event (charted as a step line), not as a reading.
EVENT_TYPES = {
    'water_change':        ('Water change', '%'),
    'co2_bubble_rate':     ('CO2 bubble rate', 'bubbles/30s'),
    'fertilizer_dose':     ('Fertilizer dose set', 'ml/day'),
    'dose':                ('One-off dose', 'ml'),
    'ammonia_dose':        ('Ammonia dose', 'ppm'),
    'livestock_added':     ('Livestock added', 'fish'),
    'filter_seeded':       ('Filter seeded', None),
    'cycle_complete':      ('Cycle complete', None),
    'drop_checker_refill': ('Drop checker refill', None),
    'equipment':           ('Equipment change', None),
    'filter_clean':        ('Filter cleaning', None),
    'glass_clean':         ('Glass cleaning', None),
    'gravel_vacuum':       ('Gravel vacuum', None),
    'plant_trim':          ('Plant trimming', None),
    'task_completed':      ('Scheduled task completed', None),
    'other':               ('Other', None),
}

QUALITIES = ('ok', 'suspect', 'bad')

# Plausible range per parameter (after unit conversion). Values, mins and maxes outside it are
# rejected rather than stored, so a typo or a wrong unit gets questioned instead of charted.
RANGES = {
    'ph': (3, 10), 'ph_degassed': (3, 10),
    'ammonia': (0, 10), 'nitrite': (0, 10), 'nitrate': (0, 200),
    'kh': (0, 30), 'gh': (0, 40),
    'ec': (0, 2000), 'tds': (0, 1500),
    'temperature': (50, 100),
    'phosphate': (0, 20), 'potassium': (0, 100), 'iron': (0, 5),
}


def norm_unit(u):
    """Compare units loosely: 'uS/cm' == 'µS/cm', case and spaces ignored."""
    return (u or '').replace('µ', 'u').replace(' ', '').lower()


def canon_unit(u):
    """norm_unit plus: 'mg/L' -> 'ppm', 'ppm as X' -> 'ppm X', leading degree sign dropped."""
    u = norm_unit(u).replace('mg/l', 'ppm').lstrip('°')
    return 'ppm' + u[5:] if u.startswith('ppmas') else u


def units_match(unit, expected):
    """Same unit, allowing common spellings. A bare 'ppm'/'mg/L' is taken as the catalog's form
    (nitrate as NO3, phosphate as PO4...); a different form ('ppm NO3-N', 'ppm P') does not match."""
    u, e = canon_unit(unit), canon_unit(expected)
    if u == e or (e.startswith('ppm') and u == 'ppm'):
        return True
    return e == '%' and u == 'percent'

# Units that convert to the catalog unit: parameter -> (divisor, accepted spellings).
# KH/GH as CaCO3 -> degrees; 1 dKH = 1 dGH = 17.848 ppm CaCO3. Matched via canon_unit, so
# 'mg/L', 'ppm as CaCO3' and 'mg/L CaCO3' all count.
UNIT_CONVERSIONS = {
    'kh': (17.848, ('ppm', 'mg/L', 'ppm CaCO3', 'mg/L CaCO3')),
    'gh': (17.848, ('ppm', 'mg/L', 'ppm CaCO3', 'mg/L CaCO3')),
}


def conversion_divisor(key, unit):
    conv = UNIT_CONVERSIONS.get(key)
    if conv and canon_unit(unit) in {canon_unit(u) for u in conv[1]}:
        return conv[0]
    return None

# Days after which a parameter's latest reading counts as stale (tile fades, age turns amber).
STALE_DAYS = {
    'ec': 2, 'temperature': 2,
    'ph': 3, 'ph_degassed': 3, 'co2_drop': 3,
    'nitrate': 7, 'ammonia': 7, 'nitrite': 7, 'tds': 7,
    'kh': 14, 'gh': 14, 'phosphate': 14, 'potassium': 14, 'iron': 14,
}

# Derived, not stored as readings: degassed pH minus the in-tank pH nearest in time that day.
# Can have a target range like a parameter.
CO2_DROP = 'co2_drop'
CO2_DROP_LABEL = 'CO2 pH drop'
# A water change at least this big (%) resets the CO2 drop's degassed reference: KH changes, so a
# degassed sample from before it no longer applies. A change with no % recorded also counts.
WC_RESETS_DEGASSED_PCT = 20
TARGET_KEYS = {**{k: p[0] for k, p in PARAMETERS.items()}, CO2_DROP: CO2_DROP_LABEL}
TARGET_RANGES = {**RANGES, CO2_DROP: (0, 3)}   # plausibility for target min/max

# Tiles on the Parameters page, in fixed groups (each group starts a new row).
# 'co2_bubble_rate' is the bubble-rate event's latest setting.
TILE_GROUPS = [
    ['ec', 'nitrate', 'phosphate', 'potassium', 'iron'],
    ['kh', 'gh', 'ammonia', 'nitrite', 'tds', 'temperature'],
    ['ph', CO2_DROP, 'ph_degassed', 'co2_bubble_rate'],
]
