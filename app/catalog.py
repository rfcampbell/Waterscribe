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


def norm_unit(u):
    """Compare units loosely: 'uS/cm' == 'µS/cm', case and spaces ignored."""
    return (u or '').replace('µ', 'u').replace(' ', '').lower()


def units_match(unit, expected):
    """Same unit, allowing common spellings: 'mg/L' or bare 'ppm' for 'ppm NO3', '°dKH' for 'dKH',
    'F' for '°F', 'percent' for '%'."""
    u, e = norm_unit(unit).replace('mg/l', 'ppm'), norm_unit(expected)
    if u == e or u.lstrip('°') == e.lstrip('°'):
        return True
    if e.startswith('ppm') and u in ('ppm', e.replace('ppm', 'ppmas')):
        return True
    return e == '%' and u == 'percent'

# Imported units that convert to the catalog unit: (parameter, normalized unit) -> divisor.
# KH/GH in ppm (as CaCO3) -> degrees; 1 dKH = 1 dGH = 17.848 ppm.
UNIT_CONVERSIONS = {
    ('kh', 'ppm'): 17.848,
    ('gh', 'ppm'): 17.848,
}
