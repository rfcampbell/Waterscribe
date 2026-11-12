"""Tiles, staleness and CO2 pH-drop pairing. Pure functions, no DB:
venv/bin/python -m unittest tests.test_overview -v"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.overview import age_text, is_stale, band_state, co2_pairs, build_tiles, spark

NOW = datetime(2026, 11, 11, 20, 0)
_ids = iter(range(1, 10_000))


def R(param, value, ts, quality='ok', time_known=True, method=None, vmin=None, vmax=None):
    return SimpleNamespace(id=next(_ids), parameter=param, value=value, timestamp=ts, quality=quality,
                           time_known=time_known, method=method, value_min=vmin, value_max=vmax, notes=None)


def ago(**kw):
    return NOW - timedelta(**kw)


class Staleness(unittest.TestCase):
    def test_thresholds_per_parameter(self):
        self.assertFalse(is_stale('ec', ago(days=1, hours=23), NOW))
        self.assertTrue(is_stale('ec', ago(days=2, minutes=1), NOW))
        self.assertFalse(is_stale('nitrate', ago(days=6), NOW))
        self.assertTrue(is_stale('nitrate', ago(days=8), NOW))
        self.assertFalse(is_stale('kh', ago(days=13), NOW))
        self.assertTrue(is_stale('kh', ago(days=15), NOW))
        self.assertTrue(is_stale('co2_drop', ago(days=4), NOW))

    def test_unknown_parameter_never_stale(self):
        self.assertFalse(is_stale('nonesuch', ago(days=400), NOW))

    def test_age_text(self):
        self.assertEqual(age_text(ago(minutes=2), True, NOW), 'just now')
        self.assertEqual(age_text(ago(minutes=40), True, NOW), '40 min ago')
        self.assertEqual(age_text(ago(hours=5), True, NOW), '5 h ago')
        self.assertEqual(age_text(ago(days=2, hours=1), True, NOW), '2 d ago')
        # date-only readings are stored at noon; count calendar days, not hours
        self.assertEqual(age_text(datetime(2026, 11, 11, 12), False, NOW), 'today')
        self.assertEqual(age_text(datetime(2026, 11, 10, 12), False, NOW), 'yesterday')
        self.assertEqual(age_text(datetime(2026, 11, 8, 12), False, NOW), '3 d ago')

    def test_stale_tile_flag(self):
        tiles = build_tiles([R('ec', 300, ago(days=3)), R('nitrate', 15, ago(days=3))], {}, NOW)
        self.assertEqual({t['key']: t['stale'] for t in tiles}, {'ec': True, 'nitrate': False})


class Band(unittest.TestCase):
    def test_band_state(self):
        self.assertIsNone(band_state(5, None))
        self.assertEqual(band_state(5, (4, 6)), 'in')
        self.assertEqual(band_state(4, (4, 6)), 'in')       # inclusive
        self.assertEqual(band_state(3.9, (4, 6)), 'out')
        self.assertEqual(band_state(100, (4, None)), 'in')  # open top
        self.assertEqual(band_state(7, (None, 6)), 'out')


class Latest(unittest.TestCase):
    def test_bad_ignored_suspect_flagged(self):
        rs = [R('ec', 300, ago(days=1)), R('ec', 9999, ago(hours=1), quality='bad')]
        t = build_tiles(rs, {}, NOW)[0]
        self.assertEqual((t['value'], t['suspect']), (300, False))
        rs.append(R('ec', 310, ago(hours=2), quality='suspect'))
        t = build_tiles(rs, {}, NOW)[0]
        self.assertEqual((t['value'], t['suspect']), (310, True))

    def test_only_bad_readings_gives_no_tile(self):
        self.assertEqual(build_tiles([R('ec', 300, ago(days=1), quality='bad')], {}, NOW), [])

    def test_tile_order_and_band(self):
        rs = [R('ph', 6.8, ago(days=1)), R('nitrate', 30, ago(days=1)), R('ec', 300, ago(days=1))]
        tiles = build_tiles(rs, {'nitrate': (10, 20)}, NOW)
        self.assertEqual([t['key'] for t in tiles], ['ec', 'nitrate', 'ph'])
        self.assertEqual(tiles[1]['band'], 'out')
        self.assertIsNone(tiles[0]['band'])

    def test_spark_window_and_band(self):
        self.assertIsNone(spark([R('ec', 1, ago(days=40))], NOW))
        sp = spark([R('ec', 300, ago(days=10)), R('ec', 320, ago(days=1), quality='suspect')], NOW, (280, 330))
        self.assertEqual(len(sp['dots']), 2)
        self.assertTrue(sp['dots'][1]['suspect'])
        self.assertIsNotNone(sp['band'])

    def test_suspect_outlier_does_not_set_scale(self):
        pts = [R('ec', 512, ago(days=20), quality='suspect'), R('ec', 200, ago(days=10)), R('ec', 300, ago(days=1))]
        sp = spark(pts, NOW)
        ys = [d['y'] for d in sp['dots']]
        self.assertEqual(ys[0], ys[2])                   # clamped to the top edge, level with the max ok point
        self.assertEqual((min(ys), max(ys)), (3, 29))    # ok points span the full box


class Co2Pairing(unittest.TestCase):
    day = datetime(2026, 11, 10)

    def at(self, h, m=0):
        return self.day.replace(hour=h, minute=m)

    def test_nearest_same_day(self):
        deg = R('ph_degassed', 7.6, self.at(9))
        rs = [deg, R('ph', 6.4, self.at(7)), R('ph', 6.6, self.at(9, 20)), R('ph', 6.5, self.at(15))]
        [p] = co2_pairs(rs)
        self.assertIs(p.degassed, deg)
        self.assertEqual(p.tank.value, 6.6)
        self.assertEqual(p.value, 1.0)

    def test_tie_goes_to_earlier(self):
        rs = [R('ph_degassed', 7.5, self.at(10)), R('ph', 6.6, self.at(11)), R('ph', 6.5, self.at(9))]
        self.assertEqual(co2_pairs(rs)[0].tank.value, 6.5)

    def test_other_days_never_pair(self):
        rs = [R('ph_degassed', 7.5, self.at(0, 5)), R('ph', 6.5, self.day - timedelta(minutes=10))]
        self.assertEqual(co2_pairs(rs), [])

    def test_bad_skipped_on_either_side(self):
        rs = [R('ph_degassed', 7.5, self.at(9)), R('ph', 6.0, self.at(9), quality='bad'), R('ph', 6.5, self.at(12))]
        self.assertEqual(co2_pairs(rs)[0].tank.value, 6.5)
        rs = [R('ph_degassed', 7.5, self.at(9), quality='bad'), R('ph', 6.5, self.at(9))]
        self.assertEqual(co2_pairs(rs), [])

    def test_suspect_and_time_unknown_carry_through(self):
        rs = [R('ph_degassed', 7.5, self.at(12), time_known=False), R('ph', 6.5, self.at(9), quality='suspect')]
        [p] = co2_pairs(rs)
        self.assertEqual((p.quality, p.time_known), ('suspect', False))

    def test_tile_shows_pairing_and_goes_stale_not_hidden(self):
        old = NOW - timedelta(days=20)
        rs = [R('ph_degassed', 7.4, old), R('ph', 6.4, old.replace(hour=8))]
        [t] = [t for t in build_tiles(rs, {'co2_drop': (0.9, 1.1)}, NOW) if t['key'] == 'co2_drop']
        self.assertEqual(t['value'], 1.0)
        self.assertEqual(t['band'], 'in')
        self.assertTrue(t['stale'])
        self.assertEqual(t['pairing'].tank.value, 6.4)

    def test_no_tile_when_pairing_older_than_90_days(self):
        old = NOW - timedelta(days=91)
        rs = [R('ph_degassed', 7.4, old), R('ph', 6.4, old)]
        self.assertNotIn('co2_drop', [t['key'] for t in build_tiles(rs, {}, NOW)])


if __name__ == '__main__':
    unittest.main()
