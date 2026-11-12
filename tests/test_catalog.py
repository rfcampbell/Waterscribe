"""Catalog label rules. Pure, no DB: venv/bin/python -m unittest tests.test_catalog -v"""
import unittest

from app.catalog import PARAMETERS, SUMMARY_LABELS, TARGET_KEYS, TILE_GROUPS, CO2_DROP


class SummaryLabels(unittest.TestCase):
    def test_every_tile_value_has_one(self):
        tiles = {k for g in TILE_GROUPS for k in g if k in TARGET_KEYS}
        self.assertEqual(set(SUMMARY_LABELS), tiles | set(PARAMETERS))

    def test_unique(self):
        self.assertEqual(len(set(SUMMARY_LABELS.values())), len(SUMMARY_LABELS))

    def test_ph_labels(self):
        # "dpH" reads as delta pH, so degassed pH must not use it; delta pH is the CO2 drop's alone
        self.assertEqual(SUMMARY_LABELS['ph_degassed'], 'pH dg')
        self.assertEqual(SUMMARY_LABELS[CO2_DROP], 'ΔpH')
        self.assertNotIn('dpH', SUMMARY_LABELS.values())


if __name__ == '__main__':
    unittest.main()
