"""Reading units, conversions and plausibility ranges. Run: venv/bin/python -m unittest discover -s tests -v"""
import csv
import unittest
from pathlib import Path

from app.catalog import RANGES, PARAMETERS
from app.records import apply_reading_unit, clean_reading, reading_from_csv_row


def reading(param, value, unit=None, **extra):
    return apply_reading_unit(clean_reading({'parameter': param, 'value': value, **extra}), unit)


class Conversions(unittest.TestCase):
    def test_kh_gh_hardness_spellings_all_convert(self):
        for p in ('kh', 'gh'):
            for u in ('ppm', 'mg/L', 'ppm CaCO3', 'mg/L CaCO3', 'ppm as CaCO3', 'PPM caco3'):
                with self.subTest(p=p, unit=u):
                    r = reading(p, '71.4', u)
                    self.assertEqual(r['value'], 4.0)
                    self.assertIn(f'converted from 71.4 {u}', r['notes'])

    def test_kh_degree_spellings_are_not_converted(self):
        for u in ('dKH', '°dKH', 'dkh', ''):
            self.assertEqual(reading('kh', '4.5', u)['value'], 4.5)

    def test_kh_other_units_rejected(self):
        for u in ('dH', 'meq/L', 'mmol/L', 'ppm NO3'):
            with self.subTest(unit=u), self.assertRaisesRegex(ValueError, "KH: unit .* not accepted"):
                reading('kh', '4', u)

    def test_bare_ppm_is_taken_as_the_catalog_form(self):
        for p, u in (('nitrate', 'ppm'), ('nitrate', 'mg/L'), ('nitrate', 'ppm as NO3'), ('nitrate', 'mg/L NO3'),
                     ('phosphate', 'ppm'), ('phosphate', 'mg/L'), ('phosphate', 'ppm as PO4')):
            with self.subTest(p=p, unit=u):
                self.assertEqual(reading(p, '10', u)['value'], 10)

    def test_other_forms_rejected(self):
        for p, u in (('nitrate', 'ppm NO3-N'), ('nitrate', 'ppm N'), ('phosphate', 'ppm P'), ('ec', 'mS/cm'),
                     ('temperature', '°C'), ('ammonia', 'ppm NH4')):
            with self.subTest(p=p, unit=u), self.assertRaisesRegex(ValueError, 'not accepted'):
                reading(p, '1', u)

    def test_existing_csv_files_still_import(self):
        for f in sorted(Path.home().glob('*_readings.csv')):
            for row in csv.DictReader(open(f)):
                reading_from_csv_row(row)


class Ranges(unittest.TestCase):
    def test_every_parameter_has_a_range(self):
        self.assertEqual(set(RANGES), set(PARAMETERS))

    def test_bounds_inclusive_and_outside_rejected_for_each_parameter(self):
        for p, (lo, hi) in RANGES.items():
            label = PARAMETERS[p][0]
            with self.subTest(p=p):
                self.assertEqual(reading(p, str(lo))['value'], lo)
                self.assertEqual(reading(p, str(hi))['value'], hi)
                for bad in (lo - 0.5, hi + 0.5):
                    with self.assertRaises(ValueError) as cm:
                        reading(p, str(bad))
                    msg = str(cm.exception)
                    self.assertTrue(msg.startswith(f'{label} {bad:g}'), msg)
                    self.assertIn(f'plausible range {lo:g}–{hi:g}', msg)
                    self.assertIn('not saved', msg)

    def test_message_example(self):
        with self.assertRaises(ValueError) as cm:
            reading('ph', '70')
        self.assertEqual(str(cm.exception),
                         'pH 70 is outside the plausible range 3–10; not saved. Check the value and unit.')
        with self.assertRaises(ValueError) as cm:
            reading('ec', '3100')
        self.assertIn('EC 3100 µS/cm is outside the plausible range 0–2000 µS/cm', str(cm.exception))

    def test_range_checked_after_conversion(self):
        self.assertEqual(reading('kh', '535', 'ppm')['value'], 29.98)       # 535 ppm = 29.98 dKH: fine
        with self.assertRaisesRegex(ValueError, r'KH 33\.62 dKH, converted from 600 ppm is outside .* 0–30 dKH'):
            reading('kh', '600', 'ppm')

    def test_range_ends_checked(self):
        with self.assertRaisesRegex(ValueError, r'Nitrate 250 ppm NO3 \(range high end\) is outside'):
            reading('nitrate', '150', value_min='100', value_max='250')
        with self.assertRaisesRegex(ValueError, r'pH 2 \(range low end\)'):
            reading('ph', '5', value_min='2', value_max='6')


if __name__ == '__main__':
    unittest.main()
