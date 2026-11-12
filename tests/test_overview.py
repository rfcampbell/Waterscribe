"""Tiles, staleness and CO2 pH-drop pairing. Pure functions, no DB:
venv/bin/python -m unittest tests.test_overview -v"""
import unittest
from datetime import datetime, timedelta, time
from types import SimpleNamespace

from app.overview import (age_text, is_stale, band_state, build_tiles, spark, in_window,
                          co2_drop_at, co2_series, series)

NOW = datetime(2026, 11, 11, 20, 0)
_ids = iter(range(1, 10_000))


def R(param, value, ts, quality='ok', time_known=True, method=None, vmin=None, vmax=None):
    return SimpleNamespace(id=next(_ids), parameter=param, value=value, timestamp=ts, quality=quality,
                           time_known=time_known, method=method, value_min=vmin, value_max=vmax, notes=None)


def ago(**kw):
    return NOW - timedelta(**kw)


def flat(groups):
    return [t for g in groups for t in g]


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
        tiles = flat(build_tiles([R('ec', 300, ago(days=3)), R('nitrate', 15, ago(days=3))], {}, NOW))
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
        t = flat(build_tiles(rs, {}, NOW))[0]
        self.assertEqual((t['value'], t['suspect']), (300, False))
        rs.append(R('ec', 310, ago(hours=2), quality='suspect'))
        t = flat(build_tiles(rs, {}, NOW))[0]
        self.assertEqual((t['value'], t['suspect']), (310, True))

    def test_only_bad_readings_gives_no_tile(self):
        self.assertEqual(build_tiles([R('ec', 300, ago(days=1), quality='bad')], {}, NOW), [])

    def test_tile_groups_and_band(self):
        rs = [R(k, 1, ago(days=1)) for k in ('ph', 'temperature', 'kh', 'iron', 'nitrate', 'ec', 'ph_degassed')]
        rs.append(R('nitrate', 30, ago(hours=1)))
        bubble = SimpleNamespace(value=30, timestamp=ago(days=1), time_known=True, notes=None)
        groups = build_tiles(rs, {'nitrate': (10, 20)}, NOW, bubble=bubble)
        self.assertEqual([[t['key'] for t in g] for g in groups],
                         [['ec', 'nitrate', 'iron'], ['kh', 'temperature'], ['ph', 'ph_degassed', 'co2_bubble_rate']])
        self.assertEqual(groups[0][1]['band'], 'out')
        self.assertIsNone(groups[0][0]['band'])

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


WIN = (time(4, 45), time(13, 45))   # 100P's window


class Co2Drop(unittest.TestCase):
    """drop = latest ok degassed pH within 14 d - latest ok in-tank pH inside the CO2 window within 2 d."""

    def drop(self, rs, at=NOW, window=WIN, events=()):
        return co2_drop_at(rs, *window, at, events)[:2]

    def tile(self, rs, window=WIN, targets=None, events=()):
        return next((t for t in flat(build_tiles(rs, targets or {}, NOW, window, events=events)) if t['key'] == 'co2_drop'), None)

    def test_window_membership(self):
        on, off = WIN
        self.assertTrue(in_window(datetime(2026, 11, 11, 4, 45), on, off))     # on is inclusive
        self.assertFalse(in_window(datetime(2026, 11, 11, 13, 45), on, off))   # off is exclusive
        self.assertFalse(in_window(datetime(2026, 11, 11, 4, 44), on, off))
        # a window that crosses midnight
        self.assertTrue(in_window(datetime(2026, 11, 11, 23, 0), time(22), time(6)))
        self.assertTrue(in_window(datetime(2026, 11, 11, 5, 59), time(22), time(6)))
        self.assertFalse(in_window(datetime(2026, 11, 11, 12, 0), time(22), time(6)))

    def test_picks_latest_in_window_not_latest_overall(self):
        deg = R('ph_degassed', 7.4, ago(days=3))
        inside = R('ph', 6.4, NOW.replace(hour=10))           # 10:00, in window
        later_outside = R('ph', 7.1, NOW.replace(hour=18))    # 18:00, CO2 off: must be ignored
        d, t = self.drop([deg, inside, later_outside])
        self.assertIs(d, deg)
        self.assertIs(t, inside)
        self.assertEqual(self.tile([deg, inside, later_outside])['value'], 1.0)

    def test_unknown_time_ph_never_counts_as_in_window(self):
        rs = [R('ph_degassed', 7.4, ago(days=1)), R('ph', 6.4, NOW.replace(hour=12), time_known=False)]
        self.assertIsNone(self.drop(rs)[1])

    def test_suspect_and_bad_excluded_on_both_sides(self):
        deg_ok = R('ph_degassed', 7.4, ago(days=5))
        deg_sus = R('ph_degassed', 7.9, ago(days=1), quality='suspect')
        tank_ok = R('ph', 6.4, NOW.replace(hour=8))
        tank_bad = R('ph', 5.0, NOW.replace(hour=11), quality='bad')
        tank_sus = R('ph', 6.0, NOW.replace(hour=12), quality='suspect')
        d, t = self.drop([deg_ok, deg_sus, tank_ok, tank_bad, tank_sus])
        self.assertIs(d, deg_ok)
        self.assertIs(t, tank_ok)

    def test_two_day_limit_on_tank_ph(self):
        deg = R('ph_degassed', 7.4, datetime(2026, 11, 9, 6, 0))
        tank = R('ph', 6.4, datetime(2026, 11, 9, 10, 0))                 # in window
        self.assertIs(self.drop([deg, tank], at=datetime(2026, 11, 11, 9, 59))[1], tank)   # 1 d 23:59 later
        self.assertIsNone(self.drop([deg, tank], at=datetime(2026, 11, 11, 10, 1))[1])     # 2 d 00:01 later

    def test_fourteen_day_limit_on_degassed(self):
        tank = R('ph', 6.4, NOW.replace(hour=10))
        self.assertIsNotNone(self.drop([tank, R('ph_degassed', 7.4, ago(days=13, hours=23))])[0])
        self.assertIsNone(self.drop([tank, R('ph_degassed', 7.4, ago(days=14, minutes=1))])[0])

    def test_no_in_window_ph_shows_message_not_number(self):
        rs = [R('ph_degassed', 7.4, ago(days=1)), R('ph', 7.0, NOW.replace(hour=19))]
        t = self.tile(rs)
        self.assertIsNone(t['value'])
        self.assertEqual(t['message'], 'no in-window pH')
        self.assertTrue(t['stale'])

    def test_no_recent_degassed_says_so(self):
        t = self.tile([R('ph', 6.4, NOW.replace(hour=10)), R('ph_degassed', 7.4, ago(days=30))])
        self.assertIsNone(t['value'])
        self.assertIn('no degassed pH', t['message'])

    def test_null_window_means_no_tile(self):
        rs = [R('ph_degassed', 7.4, ago(days=1)), R('ph', 6.4, NOW.replace(hour=10))]
        self.assertIsNone(self.tile(rs, window=None))
        self.assertIsNone(self.tile(rs, window=(None, None)))
        self.assertIsNone(self.tile([], window=None))
        self.assertEqual(self.tile([], window=WIN)['message'], 'no in-window pH')   # window set: tile even without data

    def test_tile_carries_both_readings_and_band(self):
        deg, tank = R('ph_degassed', 7.45, ago(days=2)), R('ph', 6.45, NOW.replace(hour=9))
        t = self.tile([deg, tank], targets={'co2_drop': (0.9, 1.1)})
        self.assertEqual((t['pairing'].degassed, t['pairing'].tank), (deg, tank))
        self.assertEqual((t['value'], t['band']), (1.0, 'in'))

    def test_series_follows_the_rule_over_time(self):
        d1 = R('ph_degassed', 7.4, datetime(2026, 11, 1, 12))
        p1 = R('ph', 6.4, datetime(2026, 11, 2, 9))
        p_off = R('ph', 7.2, datetime(2026, 11, 2, 20))      # outside window: no new point
        d2 = R('ph_degassed', 7.6, datetime(2026, 11, 3, 7))
        rs = [d1, p1, p_off, d2]
        self.assertEqual([(p.value, p.timestamp) for p in co2_series(rs, *WIN)],
                         [(1.0, p1.timestamp), (1.2, d2.timestamp)])
        out = series('co2_drop', rs, [], {}, WIN)
        self.assertEqual(out['points'][1]['pair']['degassed']['y'], 7.6)
        self.assertEqual(series('co2_drop', rs, [], {}, None)['points'], [])


def WCH(pct, ts, time_known=True):
    return SimpleNamespace(event_type='water_change', value=pct, timestamp=ts, time_known=time_known, notes=None)


class Co2DropWaterChange(unittest.TestCase):
    """The degassed reference must be taken after the latest water change of >= 20%."""
    deg = R('ph_degassed', 7.4, ago(days=5))
    tank = R('ph', 6.4, NOW.replace(hour=10))

    def at_now(self, events, extra=()):
        return co2_drop_at([self.deg, self.tank, *extra], *WIN, NOW, events)

    def test_intervening_water_change_blocks_pairing(self):
        wc = WCH(50, ago(days=3))
        d, t, blocker = self.at_now([wc])
        self.assertIsNone(d)
        self.assertIs(t, self.tank)
        self.assertIs(blocker, wc)
        tile = next(x for x in flat(build_tiles([self.deg, self.tank], {}, NOW, WIN, events=[wc])) if x['key'] == 'co2_drop')
        self.assertIsNone(tile['value'])
        self.assertEqual(tile['message'], 'new degassed sample needed after water change')
        self.assertTrue(tile['stale'])

    def test_new_degassed_sample_after_change_allows_it(self):
        fresh = R('ph_degassed', 7.5, ago(days=2))
        d, t, blocker = self.at_now([WCH(50, ago(days=3))], [fresh])
        self.assertIs(d, fresh)
        self.assertIsNone(blocker)

    def test_sample_at_the_same_moment_as_the_change_still_blocks(self):
        same = R('ph_degassed', 7.5, ago(days=3))
        self.assertIsNone(self.at_now([WCH(50, ago(days=3))], [same])[0])

    def test_small_change_does_not_block(self):
        self.assertIs(self.at_now([WCH(19.9, ago(days=3))])[0], self.deg)
        self.assertIsNone(self.at_now([WCH(20, ago(days=3))])[0])        # 20% exactly blocks

    def test_change_without_percent_blocks(self):
        self.assertIsNone(self.at_now([WCH(None, ago(days=3))])[0])

    def test_change_before_the_sample_or_other_events_dont_block(self):
        other = SimpleNamespace(event_type='filter_clean', value=None, timestamp=ago(days=1), time_known=True, notes=None)
        self.assertIs(self.at_now([WCH(50, ago(days=6)), other])[0], self.deg)

    def test_blocked_history_points_are_omitted(self):
        d1 = R('ph_degassed', 7.4, datetime(2026, 11, 1, 6))
        p1 = R('ph', 6.4, datetime(2026, 11, 1, 9))          # before the change: kept
        p2 = R('ph', 6.5, datetime(2026, 11, 2, 9))          # after the change: not with d1, fine with d2
        d2 = R('ph_degassed', 7.6, datetime(2026, 11, 2, 12))
        p3 = R('ph', 6.6, datetime(2026, 11, 3, 9))          # new sample: kept
        wc = WCH(50, datetime(2026, 11, 1, 18))
        pts = co2_series([d1, p1, p2, d2, p3], *WIN, [wc])
        # (6.5, 7.4) would pair a post-change pH with the pre-change sample: omitted, not plotted
        self.assertEqual([(p.tank.value, p.degassed.value) for p in pts], [(6.4, 7.4), (6.5, 7.6), (6.6, 7.6)])
        out = series('co2_drop', [d1, p1, p2, d2, p3], [wc], {}, WIN)
        self.assertEqual([p['pair']['degassed']['y'] for p in out['points']], [7.4, 7.6, 7.6])
        self.assertEqual(len(co2_series([d1, p1, p2, d2, p3], *WIN)), 4)   # without the change, (6.5, 7.4) appears


class Series(unittest.TestCase):
    def test_parameter_series_includes_bad_and_events(self):
        rs = [R('ec', 300, ago(days=2)), R('ec', 999, ago(days=1), quality='bad'), R('kh', 4, ago(days=1))]
        ev = [SimpleNamespace(timestamp=ago(days=3), time_known=True, event_type='water_change', value=50, notes=None)]
        out = series('ec', rs, ev, {'ec': (280, 320)}, None)
        self.assertEqual([p['quality'] for p in out['points']], ['ok', 'bad'])
        self.assertEqual(out['events'][0]['label'], 'Water change')
        self.assertEqual(out['events'][0]['unit'], '%')
        self.assertEqual(out['target'], (280, 320))
        self.assertIsNone(series('nonesuch', rs, ev, {}, None))

    def test_bubble_rate_is_a_step_series_from_events(self):
        ev = [SimpleNamespace(timestamp=ago(days=3), time_known=True, event_type='co2_bubble_rate', value=30, notes='x'),
              SimpleNamespace(timestamp=ago(days=2), time_known=True, event_type='water_change', value=50, notes=None)]
        out = series('co2_bubble_rate', [], ev, {}, None)
        self.assertTrue(out['step'])
        self.assertEqual([p['y'] for p in out['points']], [30])


if __name__ == '__main__':
    unittest.main()
